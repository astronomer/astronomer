"""Tests for loading secrets from mounted files instead of environment variables.

The feature is cross-cutting: one toggle changes ~16 workloads, so most of these
tests sweep the whole rendered chart rather than a single template.
"""

import pytest

from tests import newest_supported_kube_version, supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart

# Secret env vars the houston family loads from files when the feature is on.
HOUSTON_SECRET_ENV_VARS = {
    "DATABASE_URL",
    "DATABASE__CONNECTION",
    "DEPLOYMENTS__DATABASE__CONNECTION",
    "REGISTRY__AUTH_HEADER",
}

# Every cronjob in the houston family, so the sweeps cover them.
ALL_CRONJOBS = {
    "houston": {
        "updateRuntimeCheck": {"enabled": True},
        "updateCheck": {"enabled": True},
        "cleanupAirflowDb": {"enabled": True},
        "cleanupClusterAudits": {"enabled": True},
        "cleanupDeployRevisions": {"enabled": True},
        "cleanupDeployments": {"enabled": True},
        "syncDataplaneClusters": {"enabled": True},
    },
    "navigator": {"enabled": True},
    "dpLink": {"enabled": True},
}

FULL_VALUES = {
    "global": {
        "plane": {"mode": "unified"},
        "metricsReporting": {"taskUsageMetrics": {"enabled": True}},
    },
    "astronomer": ALL_CRONJOBS,
}


def houston_family_pod_specs(docs):
    """Yield (workload_name, pod_spec) for every houston-family workload."""
    for doc in docs:
        name = doc["metadata"]["name"]
        if not any(part in name for part in ("houston", "navigator", "dp-link")):
            continue
        if doc["kind"] in ("Deployment", "StatefulSet", "Job"):
            yield name, doc["spec"]["template"]["spec"]
        elif doc["kind"] == "CronJob":
            yield name, doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]


def all_containers(spec):
    """Every container in a pod spec, init containers included."""
    return (spec.get("containers") or []) + (spec.get("initContainers") or [])


def secret_env_injections(docs):
    """All (workload, container, env) triples still using valueFrom.secretKeyRef."""
    return [
        (name, container["name"], env["name"])
        for name, spec in houston_family_pod_specs(docs)
        for container in all_containers(spec)
        for env in container.get("env") or []
        if env["name"] in HOUSTON_SECRET_ENV_VARS and "valueFrom" in env
    ]


def with_secrets_from_files(enabled=True, **overrides):
    """FULL_VALUES with the global toggle set, plus any extra overrides."""
    values = {
        "global": {**FULL_VALUES["global"], "secretsFromFiles": {"enabled": enabled}},
        "astronomer": {**FULL_VALUES["astronomer"]},
    }
    for key, value in overrides.items():
        values["astronomer"][key] = {**values["astronomer"].get(key, {}), **value}
    return values


class TestSecretsFromFilesDefaults:
    """With the feature off, nothing about the chart may change."""

    def test_secret_env_vars_still_injected(self):
        docs = render_chart(kube_version=newest_supported_kube_version, values=FULL_VALUES)
        injections = secret_env_injections(docs)
        assert injections, "expected the default chart to inject secrets as env vars"

        # Nothing opts into the file-based path.
        for _name, spec in houston_family_pod_specs(docs):
            for container in all_containers(spec):
                env_vars = get_env_vars_dict(container.get("env") or [])
                assert "HOUSTON_SECRETS_FROM_FILES" not in env_vars
                assert "REGISTRY__AUTH_HEADER_FILE" not in env_vars
            volume_names = {v["name"] for v in spec.get("volumes") or []}
            assert not {"houston-secrets", "navigator-secrets", "dp-link-secrets"} & volume_names


class TestSecretsFromFilesEnabled:
    """With the feature on, no houston-family secret may reach the pod spec."""

    def test_no_secret_env_vars_remain(self):
        docs = render_chart(kube_version=newest_supported_kube_version, values=with_secrets_from_files())
        assert secret_env_injections(docs) == []

    def test_every_workload_opts_in_and_mounts_its_secrets(self):
        docs = render_chart(kube_version=newest_supported_kube_version, values=with_secrets_from_files())

        workloads = list(houston_family_pod_specs(docs))
        assert len(workloads) >= 16, f"expected the whole houston family, only rendered {len(workloads)}"

        for name, spec in workloads:
            volumes = {v["name"]: v for v in spec.get("volumes") or []}
            secret_volume = next(
                (v for v in ("houston-secrets", "navigator-secrets", "dp-link-secrets") if v in volumes),
                None,
            )
            # Every houston-family workload must be wired; a new one that isn't
            # would silently keep reading secrets from the environment.
            assert secret_volume, f"{name} has no file-based secret volume"

            # The projected volume names each file after the env var it replaces.
            sources = volumes[secret_volume]["projected"]["sources"]
            paths = {item["path"] for source in sources for item in source["secret"]["items"]}
            assert "DATABASE_URL" in paths, f"{name} does not project DATABASE_URL"

            # Whichever container reads the secrets must set the gate flag.
            mounting = [c for c in spec["containers"] if any(m["name"] == secret_volume for m in c.get("volumeMounts") or [])]
            assert mounting, f"{name} defines {secret_volume} but no container mounts it"
            for container in mounting:
                env_vars = get_env_vars_dict(container["env"])
                assert env_vars["HOUSTON_SECRETS_FROM_FILES"] == "true"
                mount = next(m for m in container["volumeMounts"] if m["name"] == secret_volume)
                assert mount["mountPath"] == "/run/secrets"
                assert mount["readOnly"] is True

    def test_no_dangling_mounts_or_duplicate_mount_paths(self):
        """A mount with no matching volume, or two volumes on one path, fails to schedule."""
        docs = render_chart(kube_version=newest_supported_kube_version, values=with_secrets_from_files())

        for name, spec in houston_family_pod_specs(docs):
            volume_names = {v["name"] for v in spec.get("volumes") or []}
            for container in all_containers(spec):
                mounts = container.get("volumeMounts") or []
                for mount in mounts:
                    assert mount["name"] in volume_names, (
                        f"{name}/{container['name']} mounts {mount['name']}, which is not a pod volume"
                    )
                paths = [m["mountPath"] for m in mounts]
                assert len(paths) == len(set(paths)), f"{name}/{container['name']} mounts two volumes on one path: {paths}"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestHoustonSecretsFromFiles:
    show_only = ["charts/astronomer/templates/houston/api/houston-deployment.yaml"]

    def test_houston_projects_both_connection_env_var_names(self, kube_version):
        """DATABASE__CONNECTION and DATABASE_URL share one secret key but need separate files."""
        docs = render_chart(
            kube_version=kube_version,
            values=with_secrets_from_files(),
            show_only=self.show_only,
        )
        volumes = {v["name"]: v for v in docs[0]["spec"]["template"]["spec"]["volumes"]}
        sources = volumes["houston-secrets"]["projected"]["sources"]

        backend = next(s for s in sources if s["secret"]["items"][0]["path"] == "DATABASE__CONNECTION")
        assert backend["secret"]["items"] == [
            {"key": "connection", "path": "DATABASE__CONNECTION"},
            {"key": "connection", "path": "DATABASE_URL"},
        ]

    def test_registry_auth_header_uses_its_own_volume(self, kube_version):
        """The API is the only consumer, so it must not land in the shared volume."""
        docs = render_chart(
            kube_version=kube_version,
            values=with_secrets_from_files(),
            show_only=self.show_only,
        )
        spec = docs[0]["spec"]["template"]["spec"]
        volumes = {v["name"]: v for v in spec["volumes"]}

        shared_paths = {
            item["path"] for source in volumes["houston-secrets"]["projected"]["sources"] for item in source["secret"]["items"]
        }
        assert "REGISTRY__AUTH_HEADER" not in shared_paths

        assert volumes["houston-registry-auth-secret"]["secret"] == {
            "secretName": "release-name-registry-auth-key",
            "items": [{"key": "token", "path": "token"}],
        }

        houston = get_containers_by_name(docs[0])["houston"]
        env_vars = get_env_vars_dict(houston["env"])
        assert "REGISTRY__AUTH_HEADER" not in env_vars
        assert env_vars["REGISTRY__AUTH_HEADER_FILE"] == "/etc/houston/secrets/registry/token"
        mount = next(m for m in houston["volumeMounts"] if m["name"] == "houston-registry-auth-secret")
        assert mount == {
            "name": "houston-registry-auth-secret",
            "mountPath": "/etc/houston/secrets/registry",
            "readOnly": True,
        }

    def test_registry_auth_header_not_mounted_into_cronjobs(self, kube_version):
        """Keep the token out of the workloads that never read it."""
        docs = render_chart(
            kube_version=kube_version,
            values=with_secrets_from_files(),
            show_only=["charts/astronomer/templates/houston/cronjobs/houston-cleanup-deployments-cronjob.yaml"],
        )
        spec = docs[0]["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        assert "houston-registry-auth-secret" not in {v["name"] for v in spec["volumes"]}

    def test_wait_for_db_drops_its_unused_database_url(self, kube_version):
        """The init container runs a shell entrypoint that never reads DATABASE_URL."""
        docs = render_chart(
            kube_version=kube_version,
            values=with_secrets_from_files(),
            show_only=self.show_only,
        )
        containers = get_containers_by_name(docs[0], include_init_containers=True)
        assert "DATABASE_URL" not in get_env_vars_dict(containers["wait-for-db"]["env"])

    def test_deployments_connection_not_projected_when_set_inline(self, kube_version):
        """Don't mount a file for a secret the chart isn't using."""
        values = with_secrets_from_files()
        values["astronomer"]["houston"] = {
            **values["astronomer"]["houston"],
            "config": {"deployments": {"database": {"connection": {"host": "inline-host"}}}},
        }
        docs = render_chart(kube_version=kube_version, values=values, show_only=self.show_only)

        volumes = {v["name"]: v for v in docs[0]["spec"]["template"]["spec"]["volumes"]}
        paths = {
            item["path"] for source in volumes["houston-secrets"]["projected"]["sources"] for item in source["secret"]["items"]
        }
        assert "DEPLOYMENTS__DATABASE__CONNECTION" not in paths
        assert "DATABASE_URL" in paths


@pytest.mark.parametrize(
    "component,template,container,secret_values",
    [
        (
            "houston",
            "charts/astronomer/templates/houston/api/houston-deployment.yaml",
            "houston",
            {"secret": [{"envName": "EMAIL__SMTP_URL", "secretName": "my-smtp", "secretKey": "connection"}]},
        ),
        (
            "navigator",
            "charts/astronomer/templates/navigator/navigator-deployment.yaml",
            "navigator",
            {"secret": [{"envName": "NAV_TOKEN", "secretName": "nav-secret"}]},
        ),
        (
            "dpLink",
            "charts/astronomer/templates/dp-link/dp-link-deployment.yaml",
            "dp-link",
            {"secret": [{"envName": "DPL_TOKEN", "secretName": "dpl-secret"}]},
        ),
    ],
    ids=["houston", "navigator", "dpLink"],
)
class TestOperatorDefinedSecrets:
    """Operator-defined secret env vars, whose names the loader can't know at build time."""

    def test_secret_env_replaced_by_file_and_extra_list(self, component, template, container, secret_values):
        values = with_secrets_from_files(**{component: secret_values})
        docs = render_chart(kube_version=newest_supported_kube_version, values=values, show_only=[template])

        env_name = secret_values["secret"][0]["envName"]
        expected_key = secret_values["secret"][0].get("secretKey", "value")

        target = get_containers_by_name(docs[0])[container]
        env_vars = get_env_vars_dict(target["env"])
        assert env_name not in env_vars, "the operator's secret should no longer be an env var"
        assert env_vars["HOUSTON_SECRETS_FROM_FILES_EXTRA"] == env_name

        spec = docs[0]["spec"]["template"]["spec"]
        sources = next(v for v in spec["volumes"] if v["name"].endswith("-secrets"))["projected"]["sources"]
        operator_source = next(s for s in sources if s["secret"]["name"] == secret_values["secret"][0]["secretName"])
        assert operator_source["secret"]["items"] == [{"key": expected_key, "path": env_name}]

    def test_no_extra_list_when_no_operator_secrets(self, component, template, container, secret_values):
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=with_secrets_from_files(),
            show_only=[template],
        )
        env_vars = get_env_vars_dict(get_containers_by_name(docs[0])[container]["env"])
        assert "HOUSTON_SECRETS_FROM_FILES_EXTRA" not in env_vars


@pytest.mark.parametrize(
    "houston_enabled,dplink_enabled",
    [(False, False), (False, True), (True, False), (True, True)],
)
def test_houston_and_dplink_toggles_are_independent(houston_enabled, dplink_enabled):
    """dp-link shares houston_volumes, so its toggle must not affect houston's mount (or vice versa).

    Getting this wrong yields either two volumes on /run/secrets or a dropped env
    var with no file to replace it.
    """
    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values={
            "global": {"plane": {"mode": "unified"}},
            "astronomer": {
                "dpLink": {"enabled": True, "secretsFromFiles": {"enabled": dplink_enabled}},
                "houston": {"secretsFromFiles": {"enabled": houston_enabled}},
            },
        },
        show_only=[
            "charts/astronomer/templates/dp-link/dp-link-deployment.yaml",
            "charts/astronomer/templates/houston/api/houston-deployment.yaml",
        ],
    )

    expected = {"dp-link": dplink_enabled, "houston": houston_enabled}
    for doc in docs:
        spec = doc["spec"]["template"]["spec"]
        for container in spec["containers"]:
            if container["name"] not in expected:
                continue
            on = expected[container["name"]]
            mounts = [m["mountPath"] for m in container.get("volumeMounts") or []]
            assert mounts.count("/run/secrets") == (1 if on else 0)
            env_vars = get_env_vars_dict(container["env"])
            assert ("HOUSTON_SECRETS_FROM_FILES" in env_vars) is on
            assert ("DATABASE__CONNECTION" in env_vars) is not on


@pytest.mark.parametrize(
    "global_enabled,component_enabled,expected",
    [
        (None, None, False),
        (False, None, False),
        (True, None, True),
        (True, False, False),
        (False, True, True),
        (None, True, True),
    ],
)
def test_houston_toggle_override_precedence(global_enabled, component_enabled, expected):
    """houston.secretsFromFiles.enabled overrides global.secretsFromFiles.enabled."""
    values = {"global": {"plane": {"mode": "unified"}}, "astronomer": {}}
    if global_enabled is not None:
        values["global"]["secretsFromFiles"] = {"enabled": global_enabled}
    if component_enabled is not None:
        values["astronomer"]["houston"] = {"secretsFromFiles": {"enabled": component_enabled}}

    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=values,
        show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
    )
    env_vars = get_env_vars_dict(get_containers_by_name(docs[0])["houston"]["env"])
    assert (env_vars.get("HOUSTON_SECRETS_FROM_FILES") == "true") is expected
    assert ("DATABASE__CONNECTION" in env_vars) is not expected
