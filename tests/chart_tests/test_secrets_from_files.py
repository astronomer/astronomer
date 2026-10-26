"""Tests for loading secrets from mounted files instead of environment variables.

The feature is cross-cutting: one toggle changes ~16 workloads, so most of these
tests sweep the whole rendered chart rather than a single template.

It is also strict. A component that is on gets its secrets only from files: its
loader refuses to start if a secret it manages is also in its environment, or a
file it was pointed at is missing or empty. So the chart must never render such a
container with a secret in its env, and refuses values that would add one. The
"strict" sections at the end of this module pin both halves.
"""

import base64
import re
import subprocess
from pathlib import Path
from subprocess import CalledProcessError

import pytest
import yaml

from tests import git_root_dir, newest_supported_kube_version, supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart

# Secret env vars the houston family loads from files when the feature is on.
# CP_ID only exists under controlPlaneHA.
HOUSTON_SECRET_ENV_VARS = {
    "DATABASE_URL",
    "DATABASE__CONNECTION",
    "DEPLOYMENTS__DATABASE__CONNECTION",
    "REGISTRY__AUTH_HEADER",
    "CP_ID",
}

# The env var that turns each loader on. A container carrying one of these set to
# "true" runs that loader, so its secrets must come from files and nothing else.
LOADER_GATES = (
    "HOUSTON_SECRETS_FROM_FILES",
    "COMMANDER_SECRETS_FROM_FILES",
    "KUIPER_SECRETS_FROM_FILES",
    "DB_BOOTSTRAPPER_SECRETS_FROM_FILES",
)

# Volumes that carry a secret a component reads from a file. Scoped to the two
# Astronomer-authored loaders (houston-api and commander) deliberately: the
# postgresql, vector and external-es-proxy groups mount their own secrets under
# separate toggles and run as other UIDs, so tightening their modes needs its own
# fsGroup verification per image. They are still on 0644.
LOADER_SECRET_VOLUMES = {
    "commander-secrets",
    "db-bootstrapper-secret",
    "flightdeck-dsn-secret",
    "houston-secrets",
    "houston-registry-auth-secret",
    "navigator-secrets",
    "dp-link-secrets",
}

SECRET_FILE_MODE = 0o440


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


def loader_gates_on(container):
    """The loader gates set to "true" in a container's env."""
    env_vars = get_env_vars_dict(container.get("env") or [])
    return [gate for gate in LOADER_GATES if env_vars.get(gate) == "true"]


def secret_env_injections(docs):
    """All (workload, container, env) triples that still put a secret in the environment.

    That is a houston-family secret arriving through valueFrom, or any secretKeyRef
    at all in a container whose loader gate is on: a loader that is on refuses to
    start next to a secret in its environment, and none may reach one anyway.
    """
    found = []
    for name, spec in pod_specs(docs):
        houston_family = any(part in name for part in ("houston", "navigator", "dp-link"))
        for container in all_containers(spec):
            gated = bool(loader_gates_on(container))
            for env in container.get("env") or []:
                secret_ref = "secretKeyRef" in (env.get("valueFrom") or {})
                if (houston_family and env["name"] in HOUSTON_SECRET_ENV_VARS and "valueFrom" in env) or (gated and secret_ref):
                    found.append((name, container["name"], env["name"]))
    return found


# The ap-db-bootstrapper toggle defaults to an explicit false rather than inheriting,
# because the pinned image has no loader. "Feature fully on" sets it explicitly too --
# a null would not inherit, see test_db_bootstrapper_null_override_does_not_inherit --
# so every sweep below also covers the bootstrapper init containers.
def db_bootstrapper_toggle(enabled):
    return {"secretsFromFiles": {"enabled": enabled}}


def with_secrets_from_files(enabled=True, **overrides):
    """FULL_VALUES with the global toggle set, plus any extra overrides."""
    values = {
        "global": {
            **FULL_VALUES["global"],
            "secretsFromFiles": {"enabled": enabled},
            "dbBootstrapper": db_bootstrapper_toggle(enabled),
        },
        "astronomer": {**FULL_VALUES["astronomer"]},
    }
    for key, value in overrides.items():
        values["astronomer"][key] = {**values["astronomer"].get(key, {}), **value}
    return values


def render_failure(values, show_only=None):
    """Render expecting the chart to refuse the values; returns helm's stderr.

    pytest.raises(match=...) cannot be used here: CalledProcessError's message is
    the command line, and helm's error text is only on .stderr.
    """
    with pytest.raises(CalledProcessError) as excinfo:
        render_chart(
            kube_version=newest_supported_kube_version,
            values=values,
            show_only=show_only,
            validate_objects=False,
        )
    return excinfo.value.stderr.decode("utf-8")


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

        # API, worker, two helm hooks, nine cronjobs, navigator and dp-link. The
        # CP-HA-only houston-cp-refresh hook is covered by its own test below.
        workloads = list(houston_family_pod_specs(docs))
        assert len(workloads) >= 15, f"expected the whole houston family, only rendered {len(workloads)}"

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
                assert mount["mountPath"] == "/etc/astronomer/secrets"
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
            "defaultMode": SECRET_FILE_MODE,
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
        assert "DATABASE_URL" not in get_env_vars_dict(containers["houston-wait-for-db"]["env"])

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

    Getting this wrong yields either two volumes on /etc/astronomer/secrets or a dropped env
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
            assert mounts.count("/etc/astronomer/secrets") == (1 if on else 0)
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


# Vector Sidecar
#
# Unlike the houston loader, this uses Vector's own native `secret` directory
# backend, so it has its own toggle. Verified end to end against the pinned
# ap-vector:0.53.0 image: the ES sink's Basic auth header decoded byte-for-byte
# to the mounted file contents.

# The chart allows exactly one sink per sidecar (houston.logging.loggingSidecar.validate),
# so every case below runs once per credential-using sink rather than with both on.
VECTOR_SINKS = {
    "cloudwatch": {
        "values": {"cloudwatch": {"enabled": True, "useIRSA": False, "region": "us-east-1"}},
        "envs": {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"},
        "items": [
            {"key": "aws_access_key_id", "path": "aws_access_key_id"},
            {"key": "aws_secret_access_key", "path": "aws_secret_access_key"},
        ],
        "env_auth": {"access_key_id": "${AWS_ACCESS_KEY_ID}"},
        "file_auth": {
            "access_key_id": "SECRET[cloudwatch.aws_access_key_id]",
            "secret_access_key": "SECRET[cloudwatch.aws_secret_access_key]",
        },
    },
    "elasticsearch": {
        "values": {"elasticsearch": {"enabled": True, "endpoint": "https://es.example.com:9200"}},
        "envs": {"ES_USERNAME", "ES_PASSWORD"},
        "items": [
            {"key": "username", "path": "username"},
            {"key": "password", "path": "password"},
        ],
        "env_auth": {"password": "${ES_PASSWORD}"},
        "file_auth": {
            "strategy": "basic",
            "user": "SECRET[elasticsearch.username]",
            "password": "SECRET[elasticsearch.password]",
        },
    },
}

VECTOR_SECRET_ENVS = set().union(*(sink["envs"] for sink in VECTOR_SINKS.values()))

VECTOR_TEMPLATES = [
    (
        "api",
        "charts/astronomer/templates/houston/api/houston-deployment.yaml",
        "charts/astronomer/templates/houston/api/houston-vector-configmap.yaml",
    ),
    (
        "worker",
        "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
        "charts/astronomer/templates/houston/worker/houston-worker-vector-configmap.yaml",
    ),
]


def sidecar_values(sidecar, enabled=None):
    """Chart values for an enabled audit sidecar, with an optional secretsFromFiles setting."""
    sidecar = {"enabled": True, **sidecar}
    if enabled is not None:
        sidecar["secretsFromFiles"] = {"enabled": enabled}
    return {
        "global": {"plane": {"mode": "unified"}},
        "astronomer": {"houston": {"logging": {"loggingSidecar": sidecar}}},
    }


def vector_values(sink, enabled=None):
    """One credential-using sink on, with an optional secretsFromFiles setting."""
    return sidecar_values(VECTOR_SINKS[sink]["values"], enabled)


def vector_config(docs):
    """The parsed vector.yaml out of whichever configmap is in docs."""
    configmap = next(d for d in docs if d["kind"] == "ConfigMap")
    return yaml.safe_load(configmap["data"]["vector.yaml"])


@pytest.mark.parametrize("sink", list(VECTOR_SINKS))
@pytest.mark.parametrize("label,deployment,configmap", VECTOR_TEMPLATES, ids=[t[0] for t in VECTOR_TEMPLATES])
class TestVectorSidecarSecretsFromFiles:
    def test_defaults_keep_env_vars(self, label, deployment, configmap, sink):
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=vector_values(sink),
            show_only=[deployment, configmap],
        )
        vector = get_containers_by_name(next(d for d in docs if d["kind"] == "Deployment"))["vector"]
        env_vars = get_env_vars_dict(vector["env"])
        assert VECTOR_SINKS[sink]["envs"] <= set(env_vars)

        config = vector_config(docs)
        assert "secret" not in config
        assert VECTOR_SINKS[sink]["env_auth"].items() <= config["sinks"][sink]["auth"].items()

    def test_enabled_replaces_env_with_secret_placeholders(self, label, deployment, configmap, sink):
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=vector_values(sink, enabled=True),
            show_only=[deployment, configmap],
        )
        doc = next(d for d in docs if d["kind"] == "Deployment")
        spec = doc["spec"]["template"]["spec"]
        vector = get_containers_by_name(doc)["vector"]
        volume = f"vector-{sink}-secret"

        # No credential ever reaches the pod spec.
        assert not VECTOR_SECRET_ENVS & set(get_env_vars_dict(vector["env"]))

        volumes = {v["name"]: v for v in spec["volumes"]}
        assert volumes[volume]["secret"]["items"] == VECTOR_SINKS[sink]["items"]

        mounts = {m["name"]: m for m in vector["volumeMounts"]}
        assert mounts[volume]["mountPath"] == f"/etc/vector/secrets/{sink}"
        assert mounts[volume]["readOnly"]

        config = vector_config(docs)
        assert config["sinks"][sink]["auth"] == VECTOR_SINKS[sink]["file_auth"]

        # The backend's directory must match the mountPath it reads from.
        assert config["secret"][sink]["path"] == mounts[volume]["mountPath"]

    def test_backend_names_are_word_characters_only(self, label, deployment, configmap, sink):
        """Vector's placeholder regex is SECRET\\[([[:word:]]+)\\....\\].

        A hyphen in a backend name does not match, so the placeholder is left in
        the config verbatim and Vector ships the literal string as a credential --
        a silent failure. Confirmed against ap-vector:0.53.0.
        """
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=vector_values(sink, enabled=True),
            show_only=[deployment, configmap],
        )
        for backend in vector_config(docs)["secret"]:
            assert re.fullmatch(r"\w+", backend), f"backend {backend!r} will not be substituted"

    def test_every_backend_removes_trailing_whitespace(self, label, deployment, configmap, sink):
        """Without this, the newline a Secret mount adds becomes a trailing space.

        The value sits in a double-quoted YAML scalar, so the newline is folded to
        a space rather than dropped, and the credential is silently wrong.
        """
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=vector_values(sink, enabled=True),
            show_only=[deployment, configmap],
        )
        for name, backend in vector_config(docs)["secret"].items():
            assert backend["type"] == "directory"
            assert backend["remove_trailing_whitespace"] is True, f"{name} would keep the trailing newline"

    def test_config_change_rolls_the_pod(self, label, deployment, configmap, sink):
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=vector_values(sink, enabled=True),
            show_only=[deployment],
        )
        annotations = docs[0]["spec"]["template"]["metadata"]["annotations"]
        assert "checksum/vector-config" in annotations


@pytest.mark.parametrize("label,deployment,configmap", VECTOR_TEMPLATES, ids=[t[0] for t in VECTOR_TEMPLATES])
@pytest.mark.parametrize(
    "sidecar",
    [
        {"cloudwatch": {"enabled": True, "useIRSA": True, "region": "us-east-1"}},
        {"elasticsearch": {"enabled": True, "endpoint": "https://es:9200", "auth": {"strategy": "none"}}},
        {
            "gcpCloudLogging": {
                "enabled": True,
                "projectId": "p",
                "resource": {"location": "us-east4", "clusterName": "c"},
            }
        },
    ],
    ids=["cloudwatch_uses_irsa", "es_auth_not_basic", "only_gcp"],
)
def test_no_credentials_mounted_for_a_sink_that_needs_none(label, deployment, configmap, sidecar):
    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=sidecar_values(sidecar, enabled=True),
        show_only=[deployment, configmap],
    )
    spec = next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"]
    assert "secret" not in vector_config(docs)
    assert not {"vector-cloudwatch-secret", "vector-elasticsearch-secret"} & {v["name"] for v in spec["volumes"]}


def test_vector_toggle_is_independent_of_houston_toggle():
    """The sidecar uses Vector's native mechanism, not the houston loader."""
    values = vector_values("cloudwatch", enabled=False)
    values["astronomer"]["houston"]["secretsFromFiles"] = {"enabled": True}
    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=values,
        show_only=[
            "charts/astronomer/templates/houston/api/houston-deployment.yaml",
            "charts/astronomer/templates/houston/api/houston-vector-configmap.yaml",
        ],
    )
    doc = next(d for d in docs if d["kind"] == "Deployment")
    containers = get_containers_by_name(doc)

    # houston moved to files, vector did not.
    assert get_env_vars_dict(containers["houston"]["env"])["HOUSTON_SECRETS_FROM_FILES"] == "true"
    assert VECTOR_SINKS["cloudwatch"]["envs"] <= set(get_env_vars_dict(containers["vector"]["env"]))
    assert "secret" not in vector_config(docs)


# ── PostgreSQL ─────────────────────────────────────────────────────────────────
#
# ap-postgresql is NOT a Bitnami image -- it is a Chainguard/Wolfi build running
# docker-library's docker-entrypoint.sh, so the mechanism is that entrypoint's
# file_env() helper and the var is POSTGRES_PASSWORD_FILE. POSTGRESQL_PASSWORD_FILE
# does not exist in the image; verified by running ap-postgresql:17.9.0-1, where
# that name leaves the DB uninitialised and the container exits 1.

PG_STATEFULSETS = [
    ("master", "charts/postgresql/templates/statefulset.yaml"),
    ("slave", "charts/postgresql/templates/statefulset-slaves.yaml"),
]

PG_PASSWORD_FILE = "/etc/astronomer/secrets/postgresql-password"


def pg_values(enabled=None, **postgresql):
    values = {
        "global": {"postgresql": {"enabled": True}},
        "postgresql": {"postgresqlDatabase": "astrodb", "replication": {"enabled": True}, **postgresql},
    }
    if enabled is not None:
        values["postgresql"]["secretsFromFiles"] = {"enabled": enabled}
    return values


@pytest.mark.parametrize("label,template", PG_STATEFULSETS, ids=[t[0] for t in PG_STATEFULSETS])
class TestPostgresqlSecretsFromFiles:
    def test_defaults_keep_env_vars(self, label, template):
        docs = render_chart(kube_version=newest_supported_kube_version, values=pg_values(), show_only=[template])
        spec = docs[0]["spec"]["template"]["spec"]
        postgres = next(c for c in spec["containers"] if "postgresql" in c["name"])
        env_vars = get_env_vars_dict(postgres["env"])

        assert env_vars["POSTGRES_PASSWORD"]["secretKeyRef"]["key"] == "postgresql-password"
        assert "POSTGRES_PASSWORD_FILE" not in env_vars
        assert "postgresql-password" not in {v["name"] for v in spec.get("volumes") or []}

    def test_enabled_uses_the_file_env_var(self, label, template):
        docs = render_chart(kube_version=newest_supported_kube_version, values=pg_values(enabled=True), show_only=[template])
        spec = docs[0]["spec"]["template"]["spec"]
        postgres = next(c for c in spec["containers"] if "postgresql" in c["name"])
        env_vars = get_env_vars_dict(postgres["env"])

        assert env_vars["POSTGRES_PASSWORD_FILE"] == PG_PASSWORD_FILE
        # The Bitnami-style name would be silently ignored by this image.
        assert "POSTGRESQL_PASSWORD_FILE" not in env_vars

        volumes = {v["name"]: v for v in spec["volumes"]}
        assert volumes["postgresql-password"]["secret"]["items"] == [{"key": "postgresql-password", "path": "postgresql-password"}]
        mount = next(m for m in postgres["volumeMounts"] if m["name"] == "postgresql-password")
        assert mount["mountPath"] == PG_PASSWORD_FILE.rsplit("/", 1)[0]
        assert mount["readOnly"] is True

    @pytest.mark.parametrize("enabled", [None, False, True], ids=["unset", "off", "on"])
    def test_password_and_password_file_are_never_both_set(self, label, template, enabled):
        """The entrypoint's file_env() exits 1 if both are set, on every start.

        Verified against ap-postgresql:17.9.0-1:
          "error: both POSTGRES_PASSWORD and POSTGRES_PASSWORD_FILE are set
           (but are exclusive)"
        Emitting both would crash-loop the database, so this must stay either/or.
        """
        docs = render_chart(kube_version=newest_supported_kube_version, values=pg_values(enabled=enabled), show_only=[template])
        for container in docs[0]["spec"]["template"]["spec"]["containers"]:
            env_vars = get_env_vars_dict(container.get("env") or [])
            assert not ("POSTGRES_PASSWORD" in env_vars and "POSTGRES_PASSWORD_FILE" in env_vars)

    def test_replication_password_is_dropped_rather_than_filed(self, label, template):
        """This image has no replication support at all, so the var is already unread.

        Dropping it removes a secret from the pod spec; projecting it to a file
        would create something nothing opens.
        """
        docs = render_chart(kube_version=newest_supported_kube_version, values=pg_values(enabled=True), show_only=[template])
        spec = docs[0]["spec"]["template"]["spec"]
        postgres = next(c for c in spec["containers"] if "postgresql" in c["name"])
        env_vars = get_env_vars_dict(postgres["env"])

        assert "POSTGRES_REPLICATION_PASSWORD" not in env_vars
        assert "POSTGRES_REPLICATION_PASSWORD_FILE" not in env_vars
        projected = {item["path"] for v in spec["volumes"] if v["name"] == "postgresql-password" for item in v["secret"]["items"]}
        assert "postgresql-replication-password" not in projected


class TestPostgresqlMetricsSidecarSecretsFromFiles:
    show_only = ["charts/postgresql/templates/statefulset.yaml"]

    def test_defaults_keep_env_var(self):
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=pg_values(metrics={"enabled": True}),
            show_only=self.show_only,
        )
        metrics = next(c for c in docs[0]["spec"]["template"]["spec"]["containers"] if c["name"] == "metrics")
        assert get_env_vars_dict(metrics["env"])["DATA_SOURCE_PASS"]["secretKeyRef"]["key"] == "postgresql-password"
        assert metrics["volumeMounts"] == []

    def test_enabled_uses_data_source_pass_file(self):
        """postgres_exporter's precedence is DATA_SOURCE_NAME > *_FILE > *, and it
        TrimSpace's the file, so a Secret mount's trailing newline is handled."""
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=pg_values(enabled=True, metrics={"enabled": True}),
            show_only=self.show_only,
        )
        spec = docs[0]["spec"]["template"]["spec"]
        metrics = next(c for c in spec["containers"] if c["name"] == "metrics")
        env_vars = get_env_vars_dict(metrics["env"])

        assert env_vars["DATA_SOURCE_PASS_FILE"] == PG_PASSWORD_FILE
        assert "DATA_SOURCE_PASS" not in env_vars
        # DATA_SOURCE_NAME would take precedence over the file and silently win.
        assert "DATA_SOURCE_NAME" not in env_vars

        mount = next(m for m in metrics["volumeMounts"] if m["name"] == "postgresql-password")
        assert mount["mountPath"] == PG_PASSWORD_FILE.rsplit("/", 1)[0]
        assert mount["name"] in {v["name"] for v in spec["volumes"]}


@pytest.mark.parametrize(
    "global_enabled,component_enabled,expected",
    [(None, None, False), (True, None, True), (True, False, False), (False, True, True)],
)
def test_postgresql_toggle_override_precedence(global_enabled, component_enabled, expected):
    values = pg_values(enabled=component_enabled)
    if global_enabled is not None:
        values["global"]["secretsFromFiles"] = {"enabled": global_enabled}
    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=values,
        show_only=["charts/postgresql/templates/statefulset.yaml"],
    )
    postgres = next(c for c in docs[0]["spec"]["template"]["spec"]["containers"] if "postgresql" in c["name"])
    env_vars = get_env_vars_dict(postgres["env"])
    assert ("POSTGRES_PASSWORD_FILE" in env_vars) is expected
    assert ("POSTGRES_PASSWORD" in env_vars) is not expected


# ── external-es-proxy ──────────────────────────────────────────────────────────
#
# Neither image has a *_FILE convention, so both halves are chart-owned:
#   esproxy  (ap-openresty)   -- nginx.conf and setenv.lua are mounted over the
#                                image's copies via subPath, so the lua is ours.
#                                The credential is read once in init_by_lua_block;
#                                setenv.lua runs per request and must not do I/O.
#   awsproxy (ap-awsesproxy)  -- aws-es-proxy uses the AWS SDK default credential
#                                chain, so a shell preamble exports the values
#                                before exec. The container already runs /bin/sh -c.
#
# Both verified against the pinned images: the esproxy set
# "Basic ZXN1c2VyOmVzcGFzcw==" from a mounted file, and the preamble set both AWS
# vars to the newline-stripped file contents.

ESP_TEMPLATES = [
    "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
    "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
    "charts/external-es-proxy/templates/external-es-proxy-env-configmap.yaml",
]


def esp_values(enabled=None, **custom_logging):
    logging_values = {
        "enabled": True,
        "host": "es.example.com",
        "secretName": "my-es-creds",
        "awsSecretName": "my-aws-creds",
        **custom_logging,
    }
    if enabled is not None:
        logging_values["secretsFromFiles"] = {"enabled": enabled}
    return {"global": {"plane": {"mode": "unified"}, "customLogging": logging_values}}


def esp_docs(enabled=None, **custom_logging):
    return render_chart(
        kube_version=newest_supported_kube_version,
        values=esp_values(enabled, **custom_logging),
        show_only=ESP_TEMPLATES,
    )


def esp_parts(docs):
    deployment = next(d for d in docs if d["kind"] == "Deployment")
    configs = {}
    for d in docs:
        if d["kind"] == "ConfigMap":
            configs.update(d["data"])
    return deployment, configs


class TestExternalEsProxySecretsFromFiles:
    def test_defaults_keep_env_vars(self):
        deployment, configs = esp_parts(esp_docs())
        spec = deployment["spec"]["template"]["spec"]
        containers = {c["name"]: c for c in spec["containers"]}

        esproxy_env = get_env_vars_dict(containers["external-es-proxy"]["env"])
        assert esproxy_env["ES_SECRET_NAME"]["secretKeyRef"]["key"] == "elastic"

        aws_env = get_env_vars_dict(containers["awsproxy"]["env"])
        assert aws_env["AWS_ACCESS_KEY_ID"]["secretKeyRef"]["key"] == "aws_access_key"
        assert aws_env["AWS_SECRET_ACCESS_KEY"]["secretKeyRef"]["key"] == "aws_secret_key"
        assert containers["awsproxy"]["args"] == ["aws-es-proxy -listen :9203"]

        assert "es-secret" not in {v["name"] for v in spec["volumes"]}
        assert "init_by_lua_block" not in configs["nginx.conf"]
        assert "ES_SECRET_FROM_FILE" not in configs["setenv.lua"]

    def test_enabled_reads_both_credentials_from_files(self):
        deployment, configs = esp_parts(esp_docs(enabled=True))
        spec = deployment["spec"]["template"]["spec"]
        volumes = {v["name"]: v for v in spec["volumes"]}
        containers = {c["name"]: c for c in spec["containers"]}

        # esproxy: no env, file mounted, lua reads it at startup and encodes it.
        esproxy = containers["external-es-proxy"]
        assert "ES_SECRET_NAME" not in get_env_vars_dict(esproxy.get("env") or [])
        assert volumes["es-secret"]["secret"]["items"] == [{"key": "elastic", "path": "ES_SECRET"}]
        esproxy_mount = next(m for m in esproxy["volumeMounts"] if m["name"] == "es-secret")
        assert esproxy_mount["mountPath"] == "/etc/astronomer/secrets"
        assert esproxy_mount["readOnly"] is True

        assert "init_by_lua_block" in configs["nginx.conf"]
        assert "/etc/astronomer/secrets/ES_SECRET" in configs["nginx.conf"]
        # The `elastic` key holds raw credentials, so the lua must encode them --
        # matching the ES_SECRET_NAME branch, not the pre-encoded ES_SECRET one.
        assert "ngx.encode_base64(ES_SECRET_FROM_FILE)" in configs["setenv.lua"]

        # awsproxy: no env, a fail-closed preamble reads the files before exec.
        awsproxy = containers["awsproxy"]
        aws_env = get_env_vars_dict(awsproxy.get("env") or [])
        assert "AWS_ACCESS_KEY_ID" not in aws_env
        assert "AWS_SECRET_ACCESS_KEY" not in aws_env
        assert awsproxy["command"] == ["/bin/sh", "-c"]
        assert len(awsproxy["args"]) == 1
        script = awsproxy["args"][0]
        assert script.startswith("set -eu\n")
        assert "read_key /etc/astronomer/secrets/aws_access_key\nAWS_ACCESS_KEY_ID=$key\n" in script
        assert "read_key /etc/astronomer/secrets/aws_secret_key\nAWS_SECRET_ACCESS_KEY=$key\n" in script
        # The old one-liner: export's own exit status hid a failed cat.
        assert 'export AWS_ACCESS_KEY_ID="$(cat' not in script
        assert script.strip().endswith("exec aws-es-proxy -listen :9203")
        aws_mount = next(m for m in awsproxy["volumeMounts"] if m["name"] == "awssecret")
        assert aws_mount["mountPath"] == "/etc/astronomer/secrets"

    def test_setenv_lua_does_no_file_io_itself(self):
        """setenv.lua runs per request; reading the file there would hit the disk
        on every proxied request. The read belongs in init_by_lua_block."""
        _deployment, configs = esp_parts(esp_docs(enabled=True))
        assert "io.open" in configs["nginx.conf"]
        assert "io.open" not in configs["setenv.lua"]

    def test_inline_secret_fails_the_render_while_on(self):
        """global.customLogging.secret is a literal credential, not a Secret reference.

        The only way the esproxy can take it is the ES_SECRET environment variable,
        which strict mode forbids, so it is a render error rather than a silent
        exception to "secrets come from files". The literal below is a test fixture
        standing in for an operator-supplied value, hence the S106 suppression.
        """
        stderr = render_failure(esp_values(True, secret="cHJlLWVuY29kZWQ="), ESP_TEMPLATES)  # noqa: S106
        assert "secret-in-environment: global.customLogging.secret is an inline credential" in stderr
        assert "global.customLogging.secretName" in stderr
        assert "global.customLogging.secretsFromFiles.enabled=false" in stderr
        assert "cHJlLWVuY29kZWQ=" not in stderr

    def test_inline_secret_still_renders_while_off(self):
        """The way out: with the proxies off, the inline value is ES_SECRET, as before."""
        deployment, _configs = esp_parts(esp_docs(enabled=False, secret="cHJlLWVuY29kZWQ="))  # noqa: S106
        spec = deployment["spec"]["template"]["spec"]
        esproxy = next(c for c in spec["containers"] if c["name"] == "external-es-proxy")

        assert get_env_vars_dict(esproxy["env"])["ES_SECRET"] == "cHJlLWVuY29kZWQ="
        assert "es-secret" not in {v["name"] for v in spec["volumes"]}
        assert "es-secret" not in {m["name"] for m in esproxy["volumeMounts"]}

    def test_esproxy_fails_closed_on_a_bad_credential_file(self):
        """Mirrors federation-auth: nginx refuses to start, naming the file, when it is
        missing, unreadable or empty -- rather than proxying every request with no
        credential, which the lua used to do on a missing file."""
        _deployment, configs = esp_parts(esp_docs(enabled=True))

        init_block = configs["nginx.conf"].split("init_by_lua_block {\n")[1].split("\n  }\n")[0]
        assert "ES_SECRET_FROM_FILE = credential" in init_block, "sliced the wrong block"
        assert init_block.count("error(") == 3, "expected open, unreadable and empty to all fail closed"
        assert 'local path = "/etc/astronomer/secrets/ES_SECRET"' in init_block
        # Every failure names the file, once: io.open's own message already starts
        # with the path, so it is only prepended when that message lacks it.
        assert "if not reason:find(path, 1, true) then" in init_block
        assert 'error("external-es-proxy: cannot open credential file " .. reason)' in init_block
        assert init_block.count(".. path)") == 2
        assert 'gsub("%s+$", "")' in init_block
        assert 'if credential == "" then' in init_block

    def test_file_mode_takes_no_credential_from_the_environment(self):
        """Strict mode has no env fallback: nginx does not even pass ES_SECRET or
        ES_SECRET_NAME through to lua, and setenv.lua never reads them."""
        _deployment, configs = esp_parts(esp_docs(enabled=True))

        assert "env ES_SECRET;" not in configs["nginx.conf"]
        assert "env ES_SECRET_NAME;" not in configs["nginx.conf"]
        assert "os.getenv" not in configs["setenv.lua"]

    def test_env_mode_lua_is_unchanged(self):
        """Off, both env vars are still declared and read, exactly as before."""
        _deployment, configs = esp_parts(esp_docs(enabled=False))

        assert "env ES_SECRET;\nenv ES_SECRET_NAME;" in configs["nginx.conf"]
        assert 'os.getenv("ES_SECRET")' in configs["setenv.lua"]
        assert 'os.getenv("ES_SECRET_NAME")' in configs["setenv.lua"]

    def test_no_credential_file_is_read_without_a_secret_name(self):
        """With no secretName there is no file to read. A fail-closed read of a file
        that is never mounted would stop every such install, so there is none."""
        docs = esp_docs(enabled=True, secretName=None, awsSecretName=None)
        deployment, configs = esp_parts(docs)

        assert "init_by_lua_block" not in configs["nginx.conf"]
        assert "es-secret" not in {v["name"] for v in deployment["spec"]["template"]["spec"]["volumes"]}
        assert "os.getenv" not in configs["setenv.lua"]

    def test_no_preamble_when_aws_credentials_are_not_used(self):
        """With an IAM role instead of keys, awsproxy still renders but has no
        credentials to read, so the args must stay untouched."""
        docs = esp_docs(enabled=True, awsSecretName=None, awsIAMRole="arn:aws:iam::123:role/es")
        deployment, _configs = esp_parts(docs)
        awsproxy = next(c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == "awsproxy")
        assert awsproxy["args"] == ["aws-es-proxy -listen :9203"]
        assert "cat /etc/astronomer/secrets" not in awsproxy["args"][0]

    def test_no_dangling_mounts(self):
        deployment, _configs = esp_parts(esp_docs(enabled=True))
        spec = deployment["spec"]["template"]["spec"]
        volume_names = {v["name"] for v in spec["volumes"]}
        for container in spec["containers"]:
            for mount in container.get("volumeMounts") or []:
                assert mount["name"] in volume_names, f"{container['name']} mounts {mount['name']}"


@pytest.mark.parametrize(
    "global_enabled,component_enabled,expected",
    [(None, None, False), (True, None, True), (True, False, False), (False, True, True)],
)
def test_external_es_proxy_toggle_override_precedence(global_enabled, component_enabled, expected):
    values = esp_values(component_enabled)
    if global_enabled is not None:
        values["global"]["secretsFromFiles"] = {"enabled": global_enabled}
    docs = render_chart(kube_version=newest_supported_kube_version, values=values, show_only=ESP_TEMPLATES)
    deployment, configs = esp_parts(docs)
    esproxy = next(c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == "external-es-proxy")
    env_vars = get_env_vars_dict(esproxy.get("env") or [])
    assert ("ES_SECRET_NAME" in env_vars) is not expected
    assert ("init_by_lua_block" in configs["nginx.conf"]) is expected


class TestAwsproxyPreamble:
    """The awsproxy's shell preamble, executed rather than string-matched.

    aws-es-proxy takes its keys from the environment, so the preamble reads the
    mounted files and exports them before exec. Strict mode needs it to fail closed:
    a missing, unreadable or empty file must stop the container with a message
    naming the file, before aws-es-proxy starts without credentials. The old
    `export X="$(cat f)"` did not, because export's own success hid the failed cat.

    The rendered script runs under the local /bin/sh with the secrets directory
    pointed at a temporary one and aws-es-proxy replaced by a stub, which reports
    whether it was started with the values from the files.
    """

    ACCESS_KEY = "sff-test-access-key"
    SECRET_KEY = "sff-test-secret-key"

    @staticmethod
    def rendered_script():
        docs = esp_docs(enabled=True)
        deployment, _configs = esp_parts(docs)
        awsproxy = next(c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == "awsproxy")
        return awsproxy["args"][0]

    def run(self, tmp_path, access_key=None, secret_key=None):
        """Run the preamble with the given file contents; None leaves the file out."""
        secrets = tmp_path / "secrets"
        secrets.mkdir()
        for name, content in (("aws_access_key", access_key), ("aws_secret_key", secret_key)):
            if content is not None:
                (secrets / name).write_text(content)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "aws-es-proxy"
        stub.write_text(
            "#!/bin/sh\n"
            f'[ "$AWS_ACCESS_KEY_ID" = "{self.ACCESS_KEY}" ] && [ "$AWS_SECRET_ACCESS_KEY" = "{self.SECRET_KEY}" ]'
            ' && echo "started with both keys: $*" || echo "started with the wrong keys"\n'
        )
        stub.chmod(0o755)
        script = self.rendered_script().replace("/etc/astronomer/secrets", str(secrets))
        return subprocess.run(
            ["/bin/sh", "-c", script],
            capture_output=True,
            text=True,
            env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
            timeout=30,
        )

    def test_starts_with_both_keys_read_from_the_files(self, tmp_path):
        result = self.run(tmp_path, access_key=f"{self.ACCESS_KEY}\n", secret_key=self.SECRET_KEY)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "started with both keys: -listen :9203"

    def test_trims_surrounding_whitespace_and_carriage_returns(self, tmp_path):
        """A key written on Windows, or padded, is trimmed as the loaders trim theirs;
        the stub only reports success for the exact key."""
        result = self.run(tmp_path, access_key=f"  {self.ACCESS_KEY}\r\n", secret_key=f"\t{self.SECRET_KEY} \r\n")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "started with both keys: -listen :9203"

    @pytest.mark.parametrize(
        "access_key,secret_key,missing",
        [(None, SECRET_KEY, "aws_access_key"), (ACCESS_KEY, None, "aws_secret_key")],
        ids=["access-key-missing", "secret-key-missing"],
    )
    def test_exits_on_a_missing_file(self, tmp_path, access_key, secret_key, missing):
        result = self.run(tmp_path, access_key=access_key, secret_key=secret_key)
        assert result.returncode == 1
        assert result.stdout == "", "aws-es-proxy must not start"
        assert f"cannot read the AWS credential file {tmp_path}/secrets/{missing}" in result.stderr

    @pytest.mark.parametrize(
        "access_key,secret_key,empty",
        [
            ("", SECRET_KEY, "aws_access_key"),
            (ACCESS_KEY, "\n", "aws_secret_key"),
            (" \t \n", SECRET_KEY, "aws_access_key"),
            (ACCESS_KEY, "\r\n", "aws_secret_key"),
        ],
        ids=["access-key-empty", "secret-key-newline-only", "access-key-whitespace-only", "secret-key-cr-only"],
    )
    def test_exits_on_an_empty_file(self, tmp_path, access_key, secret_key, empty):
        result = self.run(tmp_path, access_key=access_key, secret_key=secret_key)
        assert result.returncode == 1
        assert result.stdout == "", "aws-es-proxy must not start"
        assert f"the AWS credential file {tmp_path}/secrets/{empty} is empty" in result.stderr

    def test_never_prints_a_key(self, tmp_path):
        result = self.run(tmp_path, access_key=self.ACCESS_KEY, secret_key="")
        assert result.returncode == 1
        assert self.ACCESS_KEY not in result.stdout + result.stderr


# ── Bootstrapper-managed secrets: sentinel + wait gate ─────────────────────────
#
# A `secret` volume is projected before ANY container runs and re-projected
# asynchronously, with no ordering guarantee against container start. So a pod
# must never depend on reading a Secret that a container inside that same pod
# writes. Reading via valueFrom.secretKeyRef never had this problem, because env
# is resolved per-container after all preceding init containers.
#
# Verified on kind (k8s 1.37):
#   * mounting a secret at /run/secrets makes the container fail to start
#     outright, because the service-account token mounts under
#     /var/run/secrets/... and every relevant image symlinks /var/run -> /run.
#     Hence /etc/astronomer/secrets.
#   * a RUNNING init container does observe kubelet's in-place refresh: under a
#     second when a pod-sync event drives it, up to ~60s (the kubelet sync
#     period) with no event. Hence the gate works and is normally a no-op.

SENTINEL = "__ASTRONOMER_NOT_BOOTSTRAPPED__"

# The nine houston CronJobs. No bootstrapper runs in their pods, but on a fresh
# install one can be scheduled before another pod's houston-bootstrapper has
# replaced the sentinel in houston-backend, so they are gated too.
HOUSTON_CRONJOBS = {
    "release-name-houston-update-runtime-check",
    "release-name-houston-update-check",
    "release-name-houston-cleanup-cluster-audits",
    "release-name-houston-cleanup-deploy-revisions",
    "release-name-houston-cleanup-deployments",
    "release-name-houston-cleanup-task-usage-data",
    "release-name-houston-populate-daily-task-metrics",
    "release-name-houston-populate-hourly-ta-metrics",
    "release-name-houston-sync-dataplane-clusters",
}

GATED_WORKLOADS = {
    "release-name-commander",
    "release-name-pilot",
    "release-name-houston",
    "release-name-houston-worker",
    "release-name-navigator",
    "release-name-dp-link",
    "release-name-houston-db-migrations",
    "release-name-houston-upgrade-deployments",
} | HOUSTON_CRONJOBS


def full_feature_values(enabled=True, plane="unified"):
    return {
        "global": {
            "plane": {"mode": plane},
            "secretsFromFiles": {"enabled": enabled},
            "dbBootstrapper": db_bootstrapper_toggle(enabled),
            "metricsReporting": {"taskUsageMetrics": {"enabled": True}},
        },
        "astronomer": {
            "houston": {**ALL_CRONJOBS["houston"]},
            "flightDeck": {"enabled": True},
            "pilot": {"enabled": True},
            "navigator": {"enabled": True},
            "dpLink": {"enabled": True},
        },
    }


# The sweeps below run per plane because some workloads exist in only one of them.
# prometheus-federation-auth is data-plane only, so a unified-mode-only sweep never
# rendered it and could not have caught a dangling mount or a bad mount path there.
SWEPT_PLANES = ["unified", "control", "data"]

# (plane, workload, secret) triples that dangle today, for reasons predating this
# feature. Listed rather than folded into `external` so they stay visible: each is
# a latent deadlock, not an operator-supplied Secret.
#
# registry mounts houston.jwtCertificateSecret unconditionally (unless
# registry.enableInsecureAuth, default False), but
# houston-jwt-certificate-secret.yaml is gated to the control and unified planes.
# So a data-plane install renders a registry StatefulSet whose Secret nothing
# creates, and kubelet blocks on it before running any container. Surfaced by
# parametrizing this sweep over planes; unrelated to secrets-from-files, and needs
# an owner decision (gate the mount, sync the Secret, or document a manual step).
KNOWN_DANGLING = {
    ("data", "release-name-registry", "release-name-houston-jwt-signing-certificate"),
}


def pod_specs(docs):
    for doc in docs:
        kind = doc["kind"]
        if kind in ("Deployment", "StatefulSet", "Job"):
            yield doc["metadata"]["name"], doc["spec"]["template"]["spec"]
        elif kind == "CronJob":
            yield doc["metadata"]["name"], doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]


class TestNoSecretMountEverDangles:
    """The bug this class exists to prevent.

    <release>-flightdeck-backend was mounted as a volume but created by no
    template -- its only writer was an init container inside the very pod that
    mounted it. kubelet blocks on the missing Secret before running any
    container, so the pod deadlocked permanently on a fresh install. The manifest
    is schema-valid, so only a cross-referencing check like this catches it.
    """

    @pytest.mark.parametrize("plane", SWEPT_PLANES)
    def test_every_secret_volume_source_is_created_by_the_chart(self, plane):
        docs = render_chart(kube_version=newest_supported_kube_version, values=full_feature_values(plane=plane))
        created = {d["metadata"]["name"] for d in docs if d["kind"] == "Secret"}

        # Secrets an operator supplies, or that live outside this chart.
        external = {"astronomer-bootstrap", "release-name-tls", "astronomer-tls"}

        def secret_sources(volume):
            if isinstance(volume.get("secret"), dict):
                yield volume["secret"]["secretName"]
            for source in (volume.get("projected") or {}).get("sources") or []:
                if "secret" in source:
                    yield source["secret"]["name"]

        missing = [
            f"{name} mounts {secret_name}, which no template creates"
            for name, spec in pod_specs(docs)
            for volume in spec.get("volumes") or []
            for secret_name in secret_sources(volume)
            if secret_name not in created and secret_name not in external and (plane, name, secret_name) not in KNOWN_DANGLING
        ]
        assert missing == [], "\n".join(missing)

    def test_the_known_dangling_mount_still_dangles(self):
        """Fails once the registry/data-plane bug below is fixed, so the
        exception cannot outlive it. Delete both this test and the entry.
        """
        docs = render_chart(kube_version=newest_supported_kube_version, values=full_feature_values(plane="data"))
        created = {d["metadata"]["name"] for d in docs if d["kind"] == "Secret"}

        for plane, workload, secret_name in KNOWN_DANGLING:
            assert plane == "data"
            mounted = any(
                (v.get("secret") or {}).get("secretName") == secret_name
                for name, spec in pod_specs(docs)
                if name == workload
                for v in spec.get("volumes") or []
            )
            assert mounted, f"{workload} no longer mounts {secret_name} -- drop this exception"
            assert secret_name not in created, f"{secret_name} is now created in the data plane -- drop this exception"


class TestBootstrapperSentinel:
    def test_sentinel_is_deterministic_across_renders(self):
        """A random placeholder re-poisons the live Secret on every upgrade and
        churns the pod checksum, forcing a roll into the placeholder."""
        values = full_feature_values()
        first = render_chart(kube_version=newest_supported_kube_version, values=values)
        second = render_chart(kube_version=newest_supported_kube_version, values=values)

        def connections(docs):
            return {
                d["metadata"]["name"]: d["data"]["connection"]
                for d in docs
                if d["kind"] == "Secret" and (d.get("data") or {}).get("connection")
            }

        assert connections(first) == connections(second)
        assert connections(first), "expected the chart to create bootstrapper-managed secrets"

    @pytest.mark.parametrize(
        "secret_name",
        ["release-name-houston-backend", "release-name-flightdeck-backend"],
    )
    def test_sentinel_secret_stays_in_the_release_manifest(self, secret_name):
        """These must NOT be `pre-install` hooks, which is what they were first
        written as.

        A hook keeps `helm upgrade` from patching the bootstrapped value back to the
        placeholder, but hook resources are absent from the release manifest -- so
        upgrading from any release that HAD this Secret in its manifest makes Helm
        delete it, and with this feature on every consumer then wedges on the missing
        volume before the bootstrapper that would recreate it can run. That is the
        same deadlock the placeholder exists to prevent, reached by upgrade rather
        than install.

        `helm.sh/resource-policy: keep` would not rescue it: Helm reads that
        annotation off the LIVE object, which the older release created without it.
        The value is instead preserved by `astronomer.bootstrapSecretConnection`,
        which re-renders whatever is already in the cluster.
        """
        docs = render_chart(kube_version=newest_supported_kube_version, values=full_feature_values())
        secret = next(d for d in docs if d["kind"] == "Secret" and d["metadata"]["name"] == secret_name)

        annotations = secret["metadata"].get("annotations") or {}
        assert "helm.sh/hook" not in annotations, (
            "a hook resource is excluded from the release manifest and gets deleted on upgrade"
        )
        # lookup returns nothing without a cluster, so a fresh render is the sentinel.
        assert base64.b64decode(secret["data"]["connection"]).decode() == SENTINEL


class TestWaitForSecretGate:
    def test_gate_present_in_every_workload_that_reads_a_bootstrapped_secret(self):
        docs = render_chart(kube_version=newest_supported_kube_version, values=full_feature_values())
        gated = {
            name for name, spec in pod_specs(docs) if any(c["name"] == "wait-for-secret" for c in spec.get("initContainers") or [])
        }
        assert GATED_WORKLOADS <= gated, f"ungated: {GATED_WORKLOADS - gated}"

    def test_gate_runs_after_any_in_pod_bootstrapper(self):
        """If the gate ran first it would read the sentinel, wait for the
        bootstrapper that has not started yet, and time out."""
        docs = render_chart(kube_version=newest_supported_kube_version, values=full_feature_values())
        for name, spec in pod_specs(docs):
            names = [c["name"] for c in spec.get("initContainers") or []]
            if "wait-for-secret" not in names:
                continue
            bootstrappers = [i for i, n in enumerate(names) if "bootstrapper" in n]
            if bootstrappers:
                assert names.index("wait-for-secret") > max(bootstrappers), f"{name}: {names}"

    def test_gate_polls_a_file_it_actually_mounts(self):
        docs = render_chart(kube_version=newest_supported_kube_version, values=full_feature_values())
        for name, spec in pod_specs(docs):
            gate = next((c for c in spec.get("initContainers") or [] if c["name"] == "wait-for-secret"), None)
            if not gate:
                continue
            volume_names = {v["name"] for v in spec["volumes"]}
            mount = gate["volumeMounts"][0]
            assert mount["name"] in volume_names, f"{name}: gate mounts {mount['name']}"
            script = gate["command"][-1] if len(gate["command"]) > 2 else gate["args"][0]
            assert mount["mountPath"] in script, f"{name}: gate polls a path it does not mount"
            assert SENTINEL in script, f"{name}: gate does not compare against the sentinel"

    def test_no_gate_when_the_feature_is_off(self):
        docs = render_chart(kube_version=newest_supported_kube_version, values=full_feature_values(enabled=False))
        for name, spec in pod_specs(docs):
            names = [c["name"] for c in spec.get("initContainers") or []]
            assert "wait-for-secret" not in names, name


@pytest.mark.parametrize("houston_on", [True, False], ids=["houston-on", "houston-off"])
def test_every_houston_cronjob_is_gated_exactly_while_houston_reads_files(houston_on):
    """With houston on, each CronJob polls the file its loader will read until it no
    longer holds the sentinel, after the CA copier and before the job container. With
    houston off (the platform-wide toggle still on) none is gated: secretKeyRef waits
    for the bootstrapper on its own."""
    values = with_secrets_from_files(houston={"secretsFromFiles": {"enabled": houston_on}})
    docs = render_chart(kube_version=newest_supported_kube_version, values=values)
    specs = dict(pod_specs(docs))

    assert HOUSTON_CRONJOBS <= set(specs), f"not rendered: {sorted(HOUSTON_CRONJOBS - set(specs))}"
    for cronjob in HOUSTON_CRONJOBS:
        init = specs[cronjob].get("initContainers") or []
        gates = [c for c in init if c["name"] == "wait-for-secret"]
        if not houston_on:
            assert gates == [], f"{cronjob} is gated with houston off"
            continue
        assert [c["name"] for c in init] == ["etc-ssl-certs-copier", "wait-for-secret"], cronjob
        gate = gates[0]
        assert gate["volumeMounts"] == [{"name": "houston-secrets", "mountPath": "/etc/astronomer/secrets", "readOnly": True}]
        assert "/etc/astronomer/secrets/DATABASE_URL" in gate["command"][-1], cronjob
        assert SENTINEL in gate["command"][-1], cronjob


def test_every_gate_matches_its_pods_other_init_containers():
    """The gate honours the image's pull policy and gets the securityContext and
    resources its neighbours have -- here, each pod's CA copier, which every gated
    pod runs from the same image."""
    values = full_feature_values()
    values["astronomer"]["images"] = {"houston": {"pullPolicy": "Always"}, "commander": {"pullPolicy": "Always"}}
    docs = render_chart(kube_version=newest_supported_kube_version, values=values)

    checked = 0
    for name, spec in pod_specs(docs):
        init = {c["name"]: c for c in spec.get("initContainers") or []}
        if "wait-for-secret" not in init:
            continue
        checked += 1
        gate, copier = init["wait-for-secret"], init["etc-ssl-certs-copier"]
        assert gate["image"] == copier["image"], name
        assert gate["imagePullPolicy"] == copier["imagePullPolicy"] == "Always", name
        assert gate["securityContext"] == copier["securityContext"], name
        assert gate["securityContext"]["readOnlyRootFilesystem"] is True, name
        assert gate["resources"] == copier["resources"], name
    assert checked == len(GATED_WORKLOADS), f"checked {checked} gates"


FLIGHTDECK_BACKEND_SECRET = "release-name-flightdeck-backend"
FLIGHTDECK_SECRET_TEMPLATE = "charts/astronomer/templates/commander/commander-flightdeck-backend-secret.yaml"


def flightdeck_values(commander=None, pilot=None, global_enabled=None, plane="unified", flightdeck=True, **global_values):
    """FlightDeck and pilot on; None leaves a switch at its default."""
    values = {
        "global": {"plane": {"mode": plane}, **global_values},
        "astronomer": {"flightDeck": {"enabled": flightdeck}, "pilot": {"enabled": True}},
    }
    if plane == "data":
        values["global"]["plane"]["domainPrefix"] = "dp01"
    if global_enabled is not None:
        values["global"]["secretsFromFiles"] = {"enabled": global_enabled}
    # Built at import time for parametrize, so the switch is spelled out rather
    # than using _switch, which is defined further down.
    if commander is not None:
        values["astronomer"]["commander"] = {"secretsFromFiles": {"enabled": commander}}
    if pilot is not None:
        values["astronomer"]["pilot"] = {"enabled": True, "secretsFromFiles": {"enabled": pilot}}
    return values


def flightdeck_secret_mounters(docs):
    """Workloads that mount <release>-flightdeck-backend as a volume."""
    mounters = set()
    for name, spec in pod_specs(docs):
        for volume in spec.get("volumes") or []:
            sources = [volume["secret"].get("secretName")] if isinstance(volume.get("secret"), dict) else []
            sources += [s["secret"]["name"] for s in (volume.get("projected") or {}).get("sources") or [] if "secret" in s]
            if FLIGHTDECK_BACKEND_SECRET in sources:
                mounters.add(name)
    return mounters


class TestFlightdeckBackendSecret:
    """The placeholder exists only for a file-mode consumer, which needs the Secret
    before its pod starts. Through secretKeyRef nothing does, so with commander's and
    pilot's file mode off the bootstrapper keeps creating it at runtime, as before
    secrets-from-files -- and an upgrade does not hit Helm's ownership check on a
    Secret an older release's bootstrapper created."""

    @pytest.mark.parametrize(
        "values,rendered",
        [
            (flightdeck_values(), False),
            (flightdeck_values(global_enabled=True, commander=False, pilot=False), False),
            (flightdeck_values(global_enabled=True, flightdeck=False), False),
            (flightdeck_values(commander=True), True),
            (flightdeck_values(pilot=True), True),
            (flightdeck_values(global_enabled=True), True),
            (flightdeck_values(global_enabled=True, commander=False, plane="data", dataPlaneFailover={"enabled": True}), True),
        ],
        ids=[
            "all-off",
            "platform-on-commander-and-pilot-off",
            "flightdeck-off",
            "commander-on",
            "pilot-on",
            "platform-on",
            "pilot-on-dp-failover",
        ],
    )
    def test_rendered_only_for_a_file_mode_consumer(self, values, rendered):
        docs = render_chart(kube_version=newest_supported_kube_version, values=values, show_only=[FLIGHTDECK_SECRET_TEMPLATE])
        assert (len(docs) == 1) is rendered

    @pytest.mark.parametrize("argocd", [False, True], ids=["plain", "argocd"])
    def test_is_kept_when_it_drops_out_of_the_manifest(self, argocd):
        """It holds the only copy of the FlightDeck DB credentials; keep, as on
        cp-identity, so turning file mode or FlightDeck off, or a rollback, leaves it."""
        values = flightdeck_values(commander=True)
        values["global"]["argoCD"] = {"annotation": {"enabled": argocd}}
        docs = render_chart(kube_version=newest_supported_kube_version, values=values, show_only=[FLIGHTDECK_SECRET_TEMPLATE])
        annotations = docs[0]["metadata"]["annotations"]
        assert annotations["helm.sh/resource-policy"] == "keep"
        assert ("argocd.argoproj.io/sync-wave" in annotations) is argocd

    @pytest.mark.parametrize("argocd", [False, True], ids=["plain", "argocd"])
    def test_argocd_does_not_prune_it(self, argocd):
        """ArgoCD ignores helm.sh/resource-policy, so it needs its own instruction not
        to prune the only copy of the FlightDeck DB credentials -- and only when the
        chart's ArgoCD annotations are on."""
        values = flightdeck_values(commander=True)
        values["global"]["argoCD"] = {"annotation": {"enabled": argocd}}
        docs = render_chart(kube_version=newest_supported_kube_version, values=values, show_only=[FLIGHTDECK_SECRET_TEMPLATE])
        annotations = docs[0]["metadata"]["annotations"]
        if argocd:
            assert annotations["argocd.argoproj.io/sync-options"] == "Prune=false"
        else:
            assert "argocd.argoproj.io/sync-options" not in annotations
        # Never a hook: hook resources leave the release manifest, and the value has
        # to be preserved by re-rendering what the cluster holds.
        assert "helm.sh/hook" not in annotations
        assert base64.b64decode(docs[0]["data"]["connection"]).decode() == SENTINEL

    @pytest.mark.parametrize(
        "values",
        [
            flightdeck_values(),
            flightdeck_values(commander=True),
            flightdeck_values(pilot=True),
            flightdeck_values(global_enabled=True),
            flightdeck_values(global_enabled=True, commander=False, pilot=False),
            flightdeck_values(global_enabled=True, flightdeck=False),
            flightdeck_values(global_enabled=True, plane="data", flightdeck=False, dataPlaneFailover={"enabled": True}),
            flightdeck_values(
                global_enabled=True,
                plane="data",
                flightdeck=False,
                controlPlaneHA={"enabled": True, "globalBaseDomain": "astro.example.com"},
            ),
            flightdeck_values(pilot=True, plane="data"),
            flightdeck_values(commander=True, plane="control"),
        ],
        ids=[
            "all-off",
            "commander-on",
            "pilot-on",
            "platform-on",
            "platform-on-both-off",
            "flightdeck-off",
            "data-dp-failover",
            "data-cp-ha",
            "data-pilot-on",
            "control-plane",
        ],
    )
    def test_rendered_exactly_when_a_workload_mounts_it(self, values):
        """Pins flightdeck.backendSecretRendered to the deployments' own conditions:
        rendered without a mounter is the upgrade conflict for nothing, and a mounter
        without it is a pod stuck on FailedMount."""
        docs = render_chart(kube_version=newest_supported_kube_version, values=values)
        rendered = any(d["kind"] == "Secret" and d["metadata"]["name"] == FLIGHTDECK_BACKEND_SECRET for d in docs)
        assert rendered is bool(flightdeck_secret_mounters(docs)), f"mounted by {sorted(flightdeck_secret_mounters(docs))}"


@pytest.mark.parametrize("plane", SWEPT_PLANES)
def test_no_secret_is_mounted_under_run_secrets(plane):
    """/run/secrets is unusable: the service-account token mounts at
    /var/run/secrets/kubernetes.io/serviceaccount, every relevant image symlinks
    /var/run -> /run, and a read-only mount at /run/secrets makes runc unable to
    create that mountpoint. The container fails to start with a StartError.
    Reproduced on kind; the rendered manifest is schema-valid, so only this check
    catches it.
    """
    docs = render_chart(kube_version=newest_supported_kube_version, values=full_feature_values(plane=plane))
    offenders = []
    for name, spec in pod_specs(docs):
        for container in (spec.get("containers") or []) + (spec.get("initContainers") or []):
            for mount in container.get("volumeMounts") or []:
                path = mount["mountPath"]
                if path == "/run/secrets" or path.startswith("/run/secrets/"):
                    offenders.append(f"{name}/{container['name']} mounts {path}")
    assert offenders == [], "\n".join(offenders)


def loader_secret_volumes(spec):
    """Yield (volume_name, volume_source) for each loader secret volume in a pod."""
    for volume in spec.get("volumes") or []:
        if volume["name"] in LOADER_SECRET_VOLUMES:
            yield volume["name"], volume.get("projected") or volume.get("secret")


class TestSecretFilePermissions:
    """A mounted secret must be readable by the process and by nobody else.

    Kubernetes defaults secret volume files to 0644, which leaves the secret
    readable by every UID in the container -- most of what moving it out of the
    environment was meant to prevent. Tightening the mode alone is not enough
    though: the files are owned by root and these pods run as non-root, so
    without a matching fsGroup a 0440 file is unreadable, and a loader that is on
    refuses to start on a file it cannot read. Mode and fsGroup only make sense
    as a pair, which is what these tests check.
    """

    def test_every_loader_secret_volume_is_mode_0440(self):
        docs = render_chart(kube_version=newest_supported_kube_version, values=with_secrets_from_files())

        seen = 0
        for name, spec in houston_family_pod_specs(docs):
            for volume_name, source in loader_secret_volumes(spec):
                seen += 1
                assert source.get("defaultMode") == SECRET_FILE_MODE, (
                    f"{name}/{volume_name} has defaultMode {source.get('defaultMode')}, expected {SECRET_FILE_MODE} (0440)"
                )
        assert seen >= 15, f"expected the whole houston family, only checked {seen} volumes"

    def test_no_loader_secret_is_readable_by_other(self):
        """The bit that actually leaks the secret to unrelated UIDs."""
        docs = render_chart(kube_version=newest_supported_kube_version, values=with_secrets_from_files())

        offenders = [
            f"{name}/{volume_name} is mode {oct(source['defaultMode'])}"
            for name, spec in houston_family_pod_specs(docs)
            for volume_name, source in loader_secret_volumes(spec)
            if source.get("defaultMode", 0o644) & 0o004
        ]
        assert offenders == [], "\n".join(offenders)

    def test_every_pod_mounting_a_secret_has_a_matching_fsgroup(self):
        """The regression guard for the gap this change found.

        The workloads carrying the wait-for-secret gate were once not the same
        set as the workloads that mount a secret volume -- the houston cronjobs
        mounted one long before they were gated. Tightening the mode without
        giving those pods an fsGroup left them unable to read their own secrets,
        and nothing in the rendered manifest looks wrong. Assert against who
        mounts the volume, not against a hand-maintained list.
        """
        docs = render_chart(kube_version=newest_supported_kube_version, values=with_secrets_from_files())

        checked = 0
        for name, spec in houston_family_pod_specs(docs):
            volumes = dict(loader_secret_volumes(spec))
            if not volumes:
                continue
            checked += 1

            fs_group = (spec.get("securityContext") or {}).get("fsGroup")
            assert fs_group is not None, f"{name} mounts {sorted(volumes)} but sets no fsGroup"

            # Group read is what the fsGroup buys; without it the mode is unreadable.
            for volume_name, source in volumes.items():
                assert source["defaultMode"] & 0o040, (
                    f"{name}/{volume_name} is mode {oct(source['defaultMode'])}, which the fsGroup cannot read"
                )
        assert checked >= 15, f"expected the whole houston family, only checked {checked}"

    def test_no_fsgroup_is_added_when_the_feature_is_off(self):
        """The default path must stay byte-identical."""
        docs = render_chart(kube_version=newest_supported_kube_version, values=FULL_VALUES)

        for name, spec in houston_family_pod_specs(docs):
            assert (spec.get("securityContext") or {}).get("fsGroup") is None, f"{name} gained an fsGroup with the feature disabled"

    def test_fsgroup_is_omitted_on_openshift(self):
        """OpenShift allocates an fsGroup per namespace through its SCC. A
        hardcoded one is rejected or overridden, and the allocated one already
        matches the process, so the mode still works."""
        values = with_secrets_from_files()
        values["global"]["openshift"] = {"enabled": True}
        docs = render_chart(kube_version=newest_supported_kube_version, values=values)

        mounting = 0
        for name, spec in houston_family_pod_specs(docs):
            if not dict(loader_secret_volumes(spec)):
                continue
            mounting += 1
            assert (spec.get("securityContext") or {}).get("fsGroup") is None, f"{name} hardcodes an fsGroup on OpenShift"
        assert mounting >= 15, f"only checked {mounting} workloads"

    def test_fsgroup_is_configurable(self):
        """Images that run as another group need to be able to change it."""
        values = with_secrets_from_files()
        values["global"]["secretsFromFiles"]["fsGroup"] = 65532
        docs = render_chart(kube_version=newest_supported_kube_version, values=values)

        groups = {
            (spec.get("securityContext") or {}).get("fsGroup")
            for _name, spec in houston_family_pod_specs(docs)
            if dict(loader_secret_volumes(spec))
        }
        assert groups == {65532}


# The wait-for-db init containers run houston-api's pure-shell bin/entrypoint and
# never start node, so the loader never runs in them and they mount no secret
# volume. While houston reads its secrets from files they get only the non-secret
# variables that entrypoint reads (houston_wait_for_db_environment), so they advertise
# nothing. They used to inherit the whole houston_environment -- the gate flag and
# every <VAR>_FILE path, with no mount behind any of them -- and needed an exemption
# here; now nothing is exempt.
WAIT_FOR_DB_CONTAINERS = {
    ("release-name-houston", "houston-wait-for-db"),
    ("release-name-houston-worker", "wait-for-db"),
    ("release-name-houston-db-migrations", "wait-for-db"),
    ("release-name-houston-upgrade-deployments", "wait-for-db"),
}

SHELL_ENTRYPOINT = "/houston/bin/entrypoint"


def test_every_file_env_var_points_inside_a_mount():
    """A `<VAR>_FILE` path with no mount behind it is fatal, not ignored.

    A loader that is on refuses to start on a file it was pointed at but cannot
    read, so a container that advertises a path it never mounts is a crash loop.
    No container is exempt, the shell-only wait-for-db containers included.
    """
    docs = render_chart(kube_version=newest_supported_kube_version, values=with_secrets_from_files())

    unsatisfied = []
    for name, spec in houston_family_pod_specs(docs):
        for container in all_containers(spec):
            env_vars = get_env_vars_dict(container.get("env") or [])
            file_paths = {k: v for k, v in env_vars.items() if k.endswith("_FILE") and v}
            mount_paths = [m["mountPath"].rstrip("/") for m in container.get("volumeMounts") or []]
            missing = sorted(
                var for var, path in file_paths.items() if not any(path == m or path.startswith(m + "/") for m in mount_paths)
            )
            if missing:
                unsatisfied.append(f"{name}/{container['name']} sets {missing} but mounts no volume containing those paths")
    assert unsatisfied == [], "\n".join(unsatisfied)

    _assert_file_env_vars_have_a_projected_file(docs)


@pytest.mark.parametrize("enabled", [True, False], ids=["houston-on", "houston-off"])
def test_wait_for_db_gets_only_what_the_shell_entrypoint_reads(enabled):
    """The five wait-for-db containers (four here, cp-refresh's below) run the shell
    entrypoint, which reads the commander, registry and NATS wait settings and no
    secret. With houston on they get exactly those plus houston.env; with it off,
    the whole houston_environment as before."""
    values = with_secrets_from_files(enabled, houston={"env": [{"name": "NATS_JETSTREAM_WAIT_TIMEOUT", "value": "120"}]})
    docs = render_chart(kube_version=newest_supported_kube_version, values=values)
    specs = dict(pod_specs(docs))

    for workload, container_name in WAIT_FOR_DB_CONTAINERS:
        container = next(c for c in all_containers(specs[workload]) if c["name"] == container_name)
        assert container["command"] == [SHELL_ENTRYPOINT]
        env_vars = get_env_vars_dict(container["env"])
        where = f"{workload}/{container_name}"

        # What bin/entrypoint reads, and the operator's houston.env, either way.
        for name in (
            "COMMANDER__HOST",
            "COMMANDER__PORT",
            "COMMANDER_WAIT_ENABLED",
            "REGISTRY__HOST",
            "REGISTRY__PORT",
            "REGISTRY_WAIT_ENABLED",
            "NATS__SERVERS",
        ):
            assert name in env_vars, f"{where} lost {name}"
        assert env_vars["NATS_JETSTREAM_WAIT_TIMEOUT"] == "120", where

        advertised = sorted(
            k for k in env_vars if k.endswith("_FILE") or k in LOADER_GATES or k == "HOUSTON_SECRETS_FROM_FILES_EXTRA"
        )
        if enabled:
            assert advertised == [], f"{where} advertises {advertised} but runs no loader and mounts no secret"
            assert not any("valueFrom" in e for e in container["env"]), f"{where} still takes a value from a ref"
            assert {m["name"] for m in container["volumeMounts"]} == {"etc-ssl-certs"}
        else:
            assert advertised == [], where
            assert env_vars["DATABASE_URL"] == {"secretKeyRef": {"name": "release-name-houston-backend", "key": "connection"}}


def test_cp_refresh_hook_mounts_what_it_advertises():
    """houston-cp-refresh only renders with controlPlaneHA on, so the sweep above never sees it.

    It includes houston_environment, so with the feature on it inherits the gate flag and
    every <VAR>_FILE path. Its main container runs `yarn refresh-cp-chart-version`, which
    imports the loader, and the loader fails closed on a path it cannot read -- so without
    the mount this post-upgrade hook fails, and with it the whole helm upgrade.
    """
    values = with_secrets_from_files()
    values["global"] = {
        **values["global"],
        "plane": {"mode": "control"},
        "controlPlaneHA": {
            "enabled": True,
            "globalBaseDomain": "astro.example.com",
            "cpId": "00000000-0000-0000-0000-000000000001",
        },
    }
    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=values,
        show_only=["charts/astronomer/templates/houston/helm-hooks/houston-cp-refresh-job.yaml"],
    )
    assert len(docs) == 1
    spec = docs[0]["spec"]["template"]["spec"]
    containers = get_containers_by_name(docs[0], include_init_containers=True)

    main = containers["refresh-cp-chart-version-job"]
    assert get_env_vars_dict(main["env"])["HOUSTON_SECRETS_FROM_FILES"] == "true"
    mounts = [m["mountPath"].rstrip("/") for m in main["volumeMounts"]]
    for var, path in get_env_vars_dict(main["env"]).items():
        if var.endswith("_FILE") and path:
            assert any(path == m or path.startswith(m + "/") for m in mounts), f"{var}={path} has no mount behind it"
    assert "houston-secrets" in {v["name"] for v in spec["volumes"]}

    # 0440 needs an fsGroup, and the file-mode consumer must wait out the sentinel.
    assert spec["securityContext"]["fsGroup"] == 1000
    init_names = [c["name"] for c in spec["initContainers"]]
    assert init_names.index("wait-for-secret") > init_names.index("houston-bootstrapper")

    # Its wait-for-db is shell-only and gets no gate, paths or CP_ID, like the other four.
    wait_for_db = containers["wait-for-db"]
    assert wait_for_db["command"] == [SHELL_ENTRYPOINT]
    wait_env = get_env_vars_dict(wait_for_db["env"])
    assert not [
        k for k in wait_env if k.endswith("_FILE") or k in LOADER_GATES or k in ("HOUSTON_SECRETS_FROM_FILES_EXTRA", "CP_ID")
    ]
    assert "COMMANDER_WAIT_ENABLED" in wait_env


def _secret_volume_filenames(volume):
    """Every filename a secret/projected volume actually places in its mount dir."""
    sources = [volume["secret"]] if isinstance(volume.get("secret"), dict) else []
    sources += [s["secret"] for s in (volume.get("projected") or {}).get("sources") or [] if "secret" in s]
    names = set()
    for source in sources:
        items = source.get("items")
        if items is None:
            # Whole-Secret mount: every key becomes a file, and the key names are
            # not knowable from the manifest. Treat as "anything could be here".
            return None
        names.update(item["path"] for item in items)
    return names


def _assert_file_env_vars_have_a_projected_file(docs):
    """A <VAR>_FILE inside a mounted directory is not enough -- the volume has to
    actually put a FILE at that path.

    This is the gap that let commander ship broken: its `_FILE` env var was emitted
    under the feature toggle alone, while the projected volume only carried the
    flightdeck DSN when FlightDeck was enabled. The path was inside
    /etc/astronomer/secrets, so a directory-level check passed, but the file was not
    there on a default install and the loader, which refuses to start on a file it
    was pointed at and cannot read, crash-looped the pod. A subPath mount places
    the one item it names at its mountPath.
    """
    dangling = []
    for name, spec in pod_specs(docs):
        volumes = {v["name"]: v for v in spec.get("volumes") or []}
        for container in all_containers(spec):
            env_vars = get_env_vars_dict(container.get("env") or [])
            for var, path in env_vars.items():
                if not var.endswith("_FILE") or not isinstance(path, str) or not path:
                    continue
                for mount in container.get("volumeMounts") or []:
                    mount_path = mount["mountPath"].rstrip("/")
                    if not (path == mount_path or path.startswith(mount_path + "/")):
                        continue
                    volume = volumes.get(mount["name"])
                    if volume is None:
                        continue
                    filenames = _secret_volume_filenames(volume)
                    if filenames is None:
                        break  # whole-Secret mount, cannot be checked statically
                    relative = path[len(mount_path) :].lstrip("/")
                    if mount.get("subPath"):
                        relative = mount["subPath"] if not relative else f"{mount['subPath']}/{relative}"
                    if relative and relative not in filenames:
                        dangling.append(
                            f"{name}/{container['name']}: {var}={path} but volume {mount['name']} projects {sorted(filenames)}"
                        )
                    break

    assert dangling == [], "\n".join(dangling)


def test_no_secret_feeding_a_loader_renders_empty():
    """An empty secret file is fatal: a loader that is on refuses to start on a file
    that trims to nothing.

    So a Secret the chart renders empty would be a pod that never starts, on every
    install. The Grafana group is already blocked on exactly this shape, where a
    bootstrap Secret defaults to `connection: ""`.

    Check the inputs rather than trusting them: every (Secret, key) pair that a
    loader volume projects must carry a non-empty value. postgresql is enabled here
    because that is what creates `astronomer-bootstrap`, the one input the
    astronomer chart does not render itself.
    """
    values = with_secrets_from_files()
    values["global"]["postgresql"] = {"enabled": True}
    docs = render_chart(kube_version=newest_supported_kube_version, values=values)

    secrets = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Secret"}

    projected = set()
    for _name, spec in houston_family_pod_specs(docs):
        for volume_name, source in loader_secret_volumes(spec):
            del volume_name
            sources = [source] if "secretName" in source else [s["secret"] for s in source["sources"]]
            for src in sources:
                secret_name = src.get("secretName") or src.get("name")
                for item in src.get("items") or []:
                    projected.add((secret_name, item["key"]))

    assert projected, "expected the loader volumes to project at least one secret key"

    problems = []
    for secret_name, key in sorted(projected):
        doc = secrets.get(secret_name)
        if doc is None:
            problems.append(f"{secret_name}/{key}: no template creates this Secret")
            continue
        raw = (doc.get("data") or {}).get(key)
        if raw is None:
            problems.append(f"{secret_name}/{key}: the Secret has no such key")
            continue
        if base64.b64decode(raw).decode(errors="replace").strip() == "":
            problems.append(f"{secret_name}/{key}: renders empty, so the loader will refuse to start")

    assert problems == [], "\n".join(problems)


FILESD_RELOADER_TEMPLATE = "charts/prometheus/templates/prometheus-statefulset.yaml"
FILESD_RELOADER_SECRET_VOLUME = "filesd-reloader-secrets"


def filesd_reloader(enabled=None, component_enabled=None):
    """Render the prometheus StatefulSet and return (pod spec, sidecar container)."""
    values = {"global": {"plane": {"mode": "unified"}}}
    if enabled is not None:
        values["global"]["secretsFromFiles"] = {"enabled": enabled}
    if component_enabled is not None:
        values["prometheus"] = {"filesdReloader": {"secretsFromFiles": {"enabled": component_enabled}}}

    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=values,
        show_only=[FILESD_RELOADER_TEMPLATE],
    )
    spec = docs[0]["spec"]["template"]["spec"]
    container = next(c for c in spec["containers"] if c["name"] == "filesd-reloader")

    return spec, container


class TestFilesdReloaderSecretsFromFiles:
    """The kuiper-reloader sidecar reads DATABASE_URL from astronomer-bootstrap."""

    def test_defaults_keep_the_env_var(self):
        spec, container = filesd_reloader()

        env_vars = get_env_vars_dict(container["env"])
        assert "DATABASE_URL" in env_vars
        assert "KUIPER_SECRETS_FROM_FILES" not in env_vars
        assert "DATABASE_URL_FILE" not in env_vars

        assert FILESD_RELOADER_SECRET_VOLUME not in {v["name"] for v in spec["volumes"]}

    def test_enabled_replaces_the_env_var_with_a_file(self):
        spec, container = filesd_reloader(enabled=True)

        env_vars = get_env_vars_dict(container["env"])
        # The plaintext secret must be gone from the pod spec entirely.
        assert "DATABASE_URL" not in env_vars
        assert env_vars["KUIPER_SECRETS_FROM_FILES"] == "true"
        # The chart owns the path rather than relying on the image's default.
        assert env_vars["DATABASE_URL_FILE"] == "/etc/astronomer/secrets/DATABASE_URL"

        volume = next(v for v in spec["volumes"] if v["name"] == FILESD_RELOADER_SECRET_VOLUME)
        assert volume["secret"]["secretName"] == "astronomer-bootstrap"
        # The file is named after the env var it replaces, which is what lets the
        # loader find it at the default path too.
        assert volume["secret"]["items"] == [{"key": "connection", "path": "DATABASE_URL"}]

        mount = next(m for m in container["volumeMounts"] if m["name"] == FILESD_RELOADER_SECRET_VOLUME)
        assert mount["mountPath"] == "/etc/astronomer/secrets"
        assert mount["readOnly"] is True

    def test_the_secret_file_is_mode_0440(self):
        spec, _container = filesd_reloader(enabled=True)

        volume = next(v for v in spec["volumes"] if v["name"] == FILESD_RELOADER_SECRET_VOLUME)
        assert volume["secret"]["defaultMode"] == SECRET_FILE_MODE

    def test_the_pods_own_fsgroup_can_read_that_mode(self):
        """This pod is the reason the shared podSecurityContext helper is not used here.

        prometheus already sets its own fsGroup (65534) for its other volumes, and
        the kuiper-reloader image runs as uid 1000. fsGroup is added to every
        container's supplementary groups, so a root:65534 file at 0440 is readable
        by that process. Applying the shared helper would override the pod's fsGroup
        with a different default and break the volumes prometheus already depends on.
        """
        spec, _container = filesd_reloader(enabled=True)

        fs_group = spec["securityContext"]["fsGroup"]
        assert fs_group is not None, "0440 is unreadable without an fsGroup"

        volume = next(v for v in spec["volumes"] if v["name"] == FILESD_RELOADER_SECRET_VOLUME)
        assert volume["secret"]["defaultMode"] & 0o040, "the fsGroup must be able to read the file"

        # Pin the value, so a change to prometheus's fsGroup has to be a decision.
        assert fs_group == 65534

    def test_no_wait_for_secret_gate(self):
        """astronomer-bootstrap holds a real connection string from the start.

        It is not one of the sentinel-managed Secrets an in-pod bootstrapper
        rewrites, so there is no pre-bootstrap placeholder for a file consumer to
        latch and the gate would only add startup latency.
        """
        spec, _container = filesd_reloader(enabled=True)

        init_names = [c["name"] for c in spec.get("initContainers") or []]
        assert "wait-for-secret" not in init_names

    def test_no_dangling_mount(self):
        spec, container = filesd_reloader(enabled=True)

        volume_names = {v["name"] for v in spec["volumes"]}
        for mount in container["volumeMounts"]:
            assert mount["name"] in volume_names

        paths = [m["mountPath"] for m in container["volumeMounts"]]
        assert len(paths) == len(set(paths))

    def test_prometheus_container_is_untouched(self):
        """Only the sidecar reads this secret; it must not leak into prometheus."""
        spec, _sidecar = filesd_reloader(enabled=True)

        prometheus = next(c for c in spec["containers"] if c["name"] == "prometheus")
        mounts = {m["name"] for m in prometheus.get("volumeMounts") or []}
        assert FILESD_RELOADER_SECRET_VOLUME not in mounts

        env_vars = get_env_vars_dict(prometheus.get("env") or [])
        assert "KUIPER_SECRETS_FROM_FILES" not in env_vars


@pytest.mark.parametrize(
    "global_enabled,component_enabled,expected",
    [
        (False, None, False),
        (True, None, True),
        (False, True, True),
        (True, False, False),
        (None, True, True),
        (None, None, False),
    ],
)
def test_filesd_reloader_toggle_override_precedence(global_enabled, component_enabled, expected):
    """The component toggle wins when set; otherwise the global one applies."""
    _spec, container = filesd_reloader(enabled=global_enabled, component_enabled=component_enabled)

    env_vars = get_env_vars_dict(container["env"])
    assert ("KUIPER_SECRETS_FROM_FILES" in env_vars) is expected
    assert ("DATABASE_URL" in env_vars) is not expected


FEDERATION_AUTH_DEPLOYMENT = "charts/prometheus/templates/prometheus-federation-auth-deployment.yaml"
FEDERATION_AUTH_CONFIGMAP = "charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"
FEDERATION_AUTH_SECRET_VOLUME = "federation-auth-secrets"
FEDERATION_AUTH_TOKEN_FILE = "/etc/astronomer/secrets/REGISTRY_AUTH_TOKEN"


def federation_auth(enabled=None, component_enabled=None):
    """Render the data-plane federation-auth Deployment and its nginx ConfigMap.

    Returns (pod spec, container, nginx.conf). This workload exists only in the
    data plane, which is why it needs its own renderer rather than reusing the
    unified-mode helpers above.
    """
    values = {"global": {"plane": {"mode": "data"}}}
    if enabled is not None:
        values["global"]["secretsFromFiles"] = {"enabled": enabled}
    if component_enabled is not None:
        values["prometheus"] = {"federation": {"auth": {"secretsFromFiles": {"enabled": component_enabled}}}}

    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=values,
        show_only=[FEDERATION_AUTH_DEPLOYMENT, FEDERATION_AUTH_CONFIGMAP],
    )
    deployment = next(d for d in docs if d["kind"] == "Deployment")
    configmap = next(d for d in docs if d["kind"] == "ConfigMap")
    spec = deployment["spec"]["template"]["spec"]
    container = next(c for c in spec["containers"] if c["name"] == "federation-auth")

    return spec, container, configmap["data"]["nginx.conf"]


class TestFederationAuthSecretsFromFiles:
    """The data-plane federation-auth proxy validates a bearer token against
    registry.authHeaderSecret. The lua that reads it ships in this chart's
    ConfigMap, so switching to a file needs no ap-openresty rebuild.
    """

    def test_defaults_keep_the_env_var(self):
        spec, container, nginx_conf = federation_auth()

        env_vars = get_env_vars_dict(container["env"])
        assert env_vars["REGISTRY_AUTH_TOKEN"]["secretKeyRef"]["key"] == "token"
        assert "REGISTRY_AUTH_TOKEN_FILE" not in env_vars

        assert "env REGISTRY_AUTH_TOKEN;" in nginx_conf
        assert 'os.getenv("REGISTRY_AUTH_TOKEN")' in nginx_conf
        assert "init_by_lua_block" not in nginx_conf

        assert FEDERATION_AUTH_SECRET_VOLUME not in {v["name"] for v in spec["volumes"]}

    def test_enabled_replaces_the_env_var_with_a_file(self):
        spec, container, _nginx_conf = federation_auth(enabled=True)

        env_vars = get_env_vars_dict(container["env"])
        # The plaintext token must be gone from the pod spec entirely.
        assert "REGISTRY_AUTH_TOKEN" not in env_vars
        # The chart owns the path rather than relying on the lua's default.
        assert env_vars["REGISTRY_AUTH_TOKEN_FILE"] == FEDERATION_AUTH_TOKEN_FILE

        volume = next(v for v in spec["volumes"] if v["name"] == FEDERATION_AUTH_SECRET_VOLUME)
        assert volume["secret"]["secretName"] == "release-name-registry-auth-key"
        # The file is named after the env var it replaces, so the lua's default
        # path finds it even if the _FILE var were ever dropped.
        assert volume["secret"]["items"] == [{"key": "token", "path": "REGISTRY_AUTH_TOKEN"}]

        mount = next(m for m in container["volumeMounts"] if m["name"] == FEDERATION_AUTH_SECRET_VOLUME)
        assert mount["mountPath"] == "/etc/astronomer/secrets"
        assert mount["readOnly"] is True

    def test_env_key_is_never_empty(self):
        """REGISTRY_AUTH_TOKEN was this container's only env var. Dropping it
        without putting something back renders `env: null`, which fails schema
        validation -- the same trap the prometheus statefulset hit when
        FEDERATION_AUTH_TOKEN was deleted.
        """
        for kwargs in ({}, {"enabled": True}):
            _spec, container, _conf = federation_auth(**kwargs)
            assert container["env"], f"env is empty for {kwargs}"

    def test_enabled_reads_the_token_once_at_startup(self):
        """Reading per request would put a filesystem hit on every federated
        scrape, so the token is read in init_by_lua_block and cached in the
        shared dict that was already declared but unused.
        """
        _spec, _container, nginx_conf = federation_auth(enabled=True)

        assert "init_by_lua_block" in nginx_conf
        assert "lua_shared_dict federation_auth_cache" in nginx_conf
        assert 'ngx.shared.federation_auth_cache:set("registry_auth_token"' in nginx_conf
        assert 'ngx.shared.federation_auth_cache:get("registry_auth_token")' in nginx_conf

        # The env-var read must be gone, or a stale env value could win.
        assert 'os.getenv("REGISTRY_AUTH_TOKEN")' not in nginx_conf
        assert "env REGISTRY_AUTH_TOKEN;" not in nginx_conf
        assert "env REGISTRY_AUTH_TOKEN_FILE;" in nginx_conf

    def test_enabled_fails_closed_on_a_bad_token_file(self):
        """Verified against openresty/openresty:alpine: with the file missing,
        empty or whitespace-only, nginx refuses to start and logs the path. The
        alternative is coming up and answering every scrape with a misleading
        403.
        """
        _spec, _container, nginx_conf = federation_auth(enabled=True)

        init_block = nginx_conf.split("init_by_lua_block")[1].split("\n        }")[0]
        assert init_block.count("error(") == 3, "expected open, unreadable and empty to all fail closed"
        # The message has to name the path, or an operator cannot act on it.
        assert "path" in init_block

    def test_enabled_trims_the_trailing_newline(self):
        """A Secret mount adds a newline; an untrimmed token never matches."""
        _spec, _container, nginx_conf = federation_auth(enabled=True)

        init_block = nginx_conf.split("init_by_lua_block")[1]
        assert 'gsub("%s+$", "")' in init_block

    def test_the_configmap_checksum_still_rolls_the_pod(self):
        """Reading once at startup is only safe because a Secret change rolls the
        pod. Both checksums must survive, or a rotated token would be served
        stale until the next unrelated restart.
        """
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values={"global": {"plane": {"mode": "data"}, "secretsFromFiles": {"enabled": True}}},
            show_only=[FEDERATION_AUTH_DEPLOYMENT],
        )
        annotations = docs[0]["spec"]["template"]["metadata"]["annotations"]
        assert "checksum/prom-auth-config" in annotations
        assert "checksum/registry-auth-secret" in annotations

    def test_no_dangling_mount(self):
        spec, container, _conf = federation_auth(enabled=True)

        volume_names = {v["name"] for v in spec["volumes"]}
        for mount in container["volumeMounts"]:
            assert mount["name"] in volume_names

        paths = [m["mountPath"] for m in container["volumeMounts"]]
        assert len(paths) == len(set(paths))

    def test_secret_file_mode_is_left_at_the_image_default(self):
        """Deliberately not 0440. This pod sets no fsGroup and ap-openresty does
        not run as root, so 0440 on a root-owned file would leave the token
        unreadable and every federated scrape would 403. Same deferred decision
        as the external-es-proxy group, which mounts secrets from this same
        image. Tightening this means verifying the image UID and adding an
        fsGroup, per LOADER_SECRET_VOLUMES above.
        """
        spec, _container, _conf = federation_auth(enabled=True)

        volume = next(v for v in spec["volumes"] if v["name"] == FEDERATION_AUTH_SECRET_VOLUME)
        assert "defaultMode" not in volume["secret"]
        assert "fsGroup" not in (spec.get("securityContext") or {})

    def test_no_wait_for_secret_gate(self):
        """registry.authHeaderSecret is rendered by the chart from the houston JWT
        certificate, not written by an in-pod bootstrapper, so there is no
        sentinel for a file consumer to latch.
        """
        spec, _container, _conf = federation_auth(enabled=True)

        init_names = [c["name"] for c in spec.get("initContainers") or []]
        assert "wait-for-secret" not in init_names


@pytest.mark.parametrize(
    "global_enabled,component_enabled,expected",
    [
        (False, None, False),
        (True, None, True),
        (False, True, True),
        (True, False, False),
        (None, True, True),
        (None, None, False),
    ],
)
def test_federation_auth_toggle_override_precedence(global_enabled, component_enabled, expected):
    """The component toggle wins when set; otherwise the global one applies."""
    _spec, container, nginx_conf = federation_auth(enabled=global_enabled, component_enabled=component_enabled)

    env_vars = get_env_vars_dict(container["env"])
    assert ("REGISTRY_AUTH_TOKEN_FILE" in env_vars) is expected
    assert ("REGISTRY_AUTH_TOKEN" in env_vars) is not expected
    assert ("init_by_lua_block" in nginx_conf) is expected


PG_EXPORTER_TEMPLATE = "charts/prometheus-postgres-exporter/templates/deployment.yaml"
PG_EXPORTER_SECRET_VOLUME = "data-source-pass"
PG_EXPORTER_PASS_FILE = "/etc/astronomer/secrets/data_source_password"


def pg_exporter_values(enabled=None, component_enabled=None, datasource=None):
    """Values for the standalone postgres-exporter.

    datasource=None keeps the chart default, which is the connectionSecret
    (DATA_SOURCE_NAME) form. Pass a dict to switch to the split
    URI/USER/PASS form.
    """
    exporter = {}
    if component_enabled is not None:
        exporter["secretsFromFiles"] = {"enabled": component_enabled}
    if datasource is not None:
        exporter["config"] = {"datasource": {"connectionSecret": None, "host": "pg.example.com", "user": "exporter", **datasource}}

    values = {"global": {"prometheusPostgresExporter": {"enabled": True}}}
    if enabled is not None:
        values["global"]["secretsFromFiles"] = {"enabled": enabled}
    if exporter:
        values["prometheus-postgres-exporter"] = exporter
    return values


def pg_exporter(enabled=None, component_enabled=None, datasource=None, show_secret=False):
    """Render the standalone postgres-exporter Deployment; see pg_exporter_values."""
    values = pg_exporter_values(enabled, component_enabled, datasource)

    show_only = [PG_EXPORTER_TEMPLATE]
    if show_secret:
        show_only.append("charts/prometheus-postgres-exporter/templates/secret.yaml")

    docs = render_chart(kube_version=newest_supported_kube_version, values=values, show_only=show_only)
    deployment = next(d for d in docs if d["kind"] == "Deployment")
    spec = deployment["spec"]["template"]["spec"]
    container = next(c for c in spec["containers"] if c["name"] == "prometheus-postgres-exporter")
    secrets = {d["metadata"]["name"] for d in docs if d["kind"] == "Secret"}

    return spec, container, secrets


# A password source is required for the split form; either of these reaches it.
EXTERNAL_PASSWORD = {"passwordSecret": {"name": "my-pg-secret", "key": "my-password-key"}}
INLINE_PASSWORD = {"password": "s3cr3t"}


class TestPostgresExporterSecretsFromFiles:
    """postgres_exporter can read the password from a file, but only in the split
    DATA_SOURCE_URI/_USER/_PASS form. Verified against the ap-postgres-exporter
    0.19.1-2 binary: it ships DATA_SOURCE_URI_FILE, _USER_FILE and _PASS_FILE, and
    no _NAME_FILE.
    """

    def test_the_dsn_form_fails_the_render_while_on(self):
        """connectionSecret is the chart default, and that path uses DATA_SOURCE_NAME,
        for which postgres_exporter has no _FILE variant: the DSN could only stay in
        the environment. Strict mode refuses that rather than leaving one component
        quietly on env vars, and points at the split form, which has a file path.
        """
        stderr = render_failure(pg_exporter_values(enabled=True), [PG_EXPORTER_TEMPLATE])
        assert "secret-in-environment: prometheus-postgres-exporter.config.datasource.connectionSecret" in stderr
        assert "DATA_SOURCE_PASS_FILE" in stderr
        assert "prometheus-postgres-exporter.secretsFromFiles.enabled=false" in stderr

    def test_the_dsn_form_still_renders_with_the_exporter_off(self):
        """The way out: the platform on, the exporter alone kept on its DSN env var."""
        _spec, container, _secrets = pg_exporter(enabled=True, component_enabled=False)

        env_vars = get_env_vars_dict(container["env"])
        assert env_vars["DATA_SOURCE_NAME"]["secretKeyRef"] == {
            "name": "astronomer-bootstrap",
            "key": "connection",
        }
        assert "DATA_SOURCE_PASS_FILE" not in env_vars

    @pytest.mark.parametrize("datasource", [EXTERNAL_PASSWORD, INLINE_PASSWORD], ids=["passwordSecret", "inline-password"])
    def test_split_form_defaults_keep_the_env_var(self, datasource):
        _spec, container, _secrets = pg_exporter(enabled=False, datasource=datasource)

        env_vars = get_env_vars_dict(container["env"])
        assert "secretKeyRef" in env_vars["DATA_SOURCE_PASS"]
        assert "DATA_SOURCE_PASS_FILE" not in env_vars

    def test_split_form_enabled_reads_an_external_secret_from_a_file(self):
        spec, container, _secrets = pg_exporter(enabled=True, datasource=EXTERNAL_PASSWORD)

        env_vars = get_env_vars_dict(container["env"])
        assert "DATA_SOURCE_PASS" not in env_vars
        assert env_vars["DATA_SOURCE_PASS_FILE"] == PG_EXPORTER_PASS_FILE
        # The other two stay env vars: neither is a secret.
        assert "DATA_SOURCE_URI" in env_vars
        assert env_vars["DATA_SOURCE_USER"] == "exporter"

        volume = next(v for v in spec["volumes"] if v["name"] == PG_EXPORTER_SECRET_VOLUME)
        assert volume["secret"]["secretName"] == "my-pg-secret"
        # The operator's key name is remapped to the filename the env var points at.
        assert volume["secret"]["items"] == [{"key": "my-password-key", "path": "data_source_password"}]

        mount = next(m for m in container["volumeMounts"] if m["name"] == PG_EXPORTER_SECRET_VOLUME)
        assert mount["mountPath"] == "/etc/astronomer/secrets"
        assert mount["readOnly"] is True

    def test_split_form_enabled_mounts_the_chart_created_secret(self):
        """With an inline password the chart creates the Secret itself, so the
        mount must name that one -- and it has to actually exist.
        """
        spec, container, secrets = pg_exporter(enabled=True, datasource=INLINE_PASSWORD, show_secret=True)

        volume = next(v for v in spec["volumes"] if v["name"] == PG_EXPORTER_SECRET_VOLUME)
        secret_name = volume["secret"]["secretName"]
        assert volume["secret"]["items"] == [{"key": "data_source_password", "path": "data_source_password"}]
        assert secret_name in secrets, f"{secret_name} is mounted but not created"

        env_vars = get_env_vars_dict(container["env"])
        assert env_vars["DATA_SOURCE_PASS_FILE"] == PG_EXPORTER_PASS_FILE

    def test_no_password_source_fails_the_render_while_on(self):
        """Neither passwordSecret nor password set: there is no file to deliver, and
        the only form left is a secretKeyRef on a Secret the chart never creates --
        a secret in the environment of a component that is on, and one that could
        not start anyway. Refused, naming what to set.
        """
        stderr = render_failure(pg_exporter_values(enabled=True, datasource={}), [PG_EXPORTER_TEMPLATE])
        assert (
            "secret-file-missing: prometheus-postgres-exporter.config.datasource sets neither passwordSecret nor password" in stderr
        )
        assert "prometheus-postgres-exporter.secretsFromFiles.enabled=false" in stderr

    def test_no_password_source_still_renders_with_the_exporter_off(self):
        """Off, it renders as it always has: no mount, the secretKeyRef as before."""
        spec, container, _secrets = pg_exporter(enabled=True, component_enabled=False, datasource={})

        assert PG_EXPORTER_SECRET_VOLUME not in {v["name"] for v in spec["volumes"]}
        env_vars = get_env_vars_dict(container["env"])
        assert "secretKeyRef" in env_vars["DATA_SOURCE_PASS"]

    def test_no_dangling_mount(self):
        spec, container, _secrets = pg_exporter(enabled=True, datasource=EXTERNAL_PASSWORD)

        volume_names = {v["name"] for v in spec["volumes"]}
        for mount in container["volumeMounts"]:
            assert mount["name"] in volume_names

        paths = [m["mountPath"] for m in container["volumeMounts"]]
        assert len(paths) == len(set(paths))

    def test_secret_file_mode_is_left_at_the_image_default(self):
        """Not 0440: the container is runAsNonRoot with no runAsUser and this pod
        sets no fsGroup, so 0440 on a root-owned file would be unreadable. Same
        deferred decision as external-es-proxy and federation-auth.
        """
        spec, _container, _secrets = pg_exporter(enabled=True, datasource=EXTERNAL_PASSWORD)

        volume = next(v for v in spec["volumes"] if v["name"] == PG_EXPORTER_SECRET_VOLUME)
        assert "defaultMode" not in volume["secret"]
        assert not (spec.get("securityContext") or {}).get("fsGroup")

    def test_the_mount_path_is_never_under_run_secrets(self):
        _spec, container, _secrets = pg_exporter(enabled=True, datasource=EXTERNAL_PASSWORD)

        for mount in container["volumeMounts"]:
            assert not mount["mountPath"].startswith("/run/secrets")
        env_vars = get_env_vars_dict(container["env"])
        assert not env_vars["DATA_SOURCE_PASS_FILE"].startswith("/run/secrets")


@pytest.mark.parametrize(
    "global_enabled,component_enabled,expected",
    [
        (False, None, False),
        (True, None, True),
        (False, True, True),
        (True, False, False),
        (None, True, True),
        (None, None, False),
    ],
)
def test_postgres_exporter_toggle_override_precedence(global_enabled, component_enabled, expected):
    """The component toggle wins when set; otherwise the global one applies."""
    _spec, container, _secrets = pg_exporter(
        enabled=global_enabled,
        component_enabled=component_enabled,
        datasource=EXTERNAL_PASSWORD,
    )

    env_vars = get_env_vars_dict(container["env"])
    assert ("DATA_SOURCE_PASS_FILE" in env_vars) is expected
    assert ("DATA_SOURCE_PASS" in env_vars) is not expected


COMMANDER_TEMPLATE = "charts/astronomer/templates/commander/commander-deployment.yaml"


@pytest.mark.parametrize(
    "extra_values,flightdeck_expected",
    [
        ({}, False),
        ({"astronomer": {"flightDeck": {"enabled": True}}}, True),
        ({"global": {"plane": {"mode": "data"}, "dataPlaneFailover": {"enabled": True}}}, True),
    ],
    ids=["flightdeck-off-default", "flightdeck-on", "dataplane-failover"],
)
def test_commander_only_advertises_the_flightdeck_dsn_file_when_flightdeck_is_on(extra_values, flightdeck_expected):
    """Regression: commander crash-looped on a DEFAULT install with the feature on.

    The `COMMANDER_FLIGHTDECK_DSN_FILE` env var was emitted under the feature toggle
    alone, while the projected volume only carries the flightdeck DSN when FlightDeck
    is enabled -- default off. The loader fails closed on a `<VAR>_FILE` it cannot
    read, so commander exited non-zero and never started. The `secretKeyRef` branch
    was always gated correctly; only the file branch was not.

    The pre-existing sweep missed it twice over: it checked the path was inside a
    mounted *directory* rather than that the volume projects a *file* there, and it
    only walked the houston family, which excludes commander.
    """
    values = {"global": {"secretsFromFiles": {"enabled": True}}}
    for key, value in extra_values.items():
        values[key] = {**values.get(key, {}), **value}

    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=values,
        show_only=[COMMANDER_TEMPLATE],
    )
    spec = docs[0]["spec"]["template"]["spec"]

    projected = {
        item["path"]
        for volume in spec["volumes"]
        if volume["name"] == "commander-secrets"
        for source in volume["projected"]["sources"]
        for item in source["secret"]["items"]
    }
    assert ("COMMANDER_FLIGHTDECK_DSN" in projected) is flightdeck_expected
    # The dataplane DSN comes from astronomer-bootstrap and is always present.
    assert "COMMANDER_DATAPLANE_DATABASE_URL" in projected

    # Only containers that actually consume the flightdeck DSN may advertise it, and
    # whether any does at all has to track the projected volume.
    advertisers = [
        container["name"]
        for container in all_containers(spec)
        if "COMMANDER_FLIGHTDECK_DSN_FILE" in get_env_vars_dict(container.get("env") or [])
    ]
    assert bool(advertisers) is flightdeck_expected, f"flightdeck DSN file advertised by {advertisers}"

    # And no container may advertise any secrets path without a file behind it.
    for container in all_containers(spec):
        for var, path in get_env_vars_dict(container.get("env") or []).items():
            if var.endswith("_FILE") and isinstance(path, str) and path.startswith("/etc/astronomer/secrets/"):
                assert path.rsplit("/", 1)[-1] in projected, f"{container['name']}: {var}={path} has no file behind it"


# Must match `secretEnvVars` in astronomer/commander config/secrets_from_files.go.
# The two repos cannot read each other in CI, so this is a deliberate mirror: if
# commander's list changes, update it here and the sweep below re-checks the chart.
COMMANDER_SECRET_ENV_VARS = {
    "COMMANDER_DATAPLANE_DATABASE_URL",
    "COMMANDER_FLIGHTDECK_DSN",
}

PILOT_TEMPLATE = "charts/astronomer/templates/pilot/pilot-deployment.yaml"


@pytest.mark.parametrize("plane", ["unified", "data"])
def test_commander_file_vars_are_all_ones_commander_loads(plane):
    """Every `<VAR>_FILE` the chart hands a commander-loader container must name a
    variable commander's loader actually reads.

    This is the dangerous direction of list drift. Under the toggle the chart drops
    the `secretKeyRef` and sets `<VAR>_FILE` instead, so if commander's
    `secretEnvVars` does not include `<VAR>`, nothing reads the file and `<VAR>`
    ends up unset -- with no error, because an unlisted `_FILE` is just an env var
    nobody looks at. Commander's own guard tests only compare its list against its
    config struct, and the live-cluster scenario that would notice is `ci: false`.
    """
    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=full_feature_values(plane=plane),
        show_only=[COMMANDER_TEMPLATE, PILOT_TEMPLATE],
    )

    advertised = set()
    unknown = []
    loader_containers = 0
    for name, spec in pod_specs(docs):
        for container in all_containers(spec):
            env_vars = get_env_vars_dict(container.get("env") or [])
            # Only containers that run commander's loader; it is gated by this var.
            if env_vars.get("COMMANDER_SECRETS_FROM_FILES") != "true":
                continue
            loader_containers += 1
            for var in env_vars:
                if not var.endswith("_FILE"):
                    continue
                target = var.removesuffix("_FILE")
                advertised.add(target)
                if target not in COMMANDER_SECRET_ENV_VARS:
                    unknown.append(f"{name}/{container['name']}: {var}")

    # Guards against the sweep silently matching nothing: commander's main and
    # migrations containers plus pilot, all with FlightDeck on.
    assert loader_containers >= 3, f"only {loader_containers} commander-loader containers rendered"
    assert unknown == [], "_FILE vars commander does not load:\n" + "\n".join(unknown)
    # And the mirror has no dead entries: with every toggle on, each listed var is
    # actually delivered as a file somewhere.
    assert advertised == COMMANDER_SECRET_ENV_VARS


# ── ap-db-bootstrapper init containers (BOOTSTRAP_DB) ──────────────────────────
#
# One image, run as an init container in three subcharts, so one global toggle:
# global.dbBootstrapper.secretsFromFiles.enabled. It defaults to an explicit false
# because the pinned image has no loader, so `global.secretsFromFiles.enabled` alone
# must leave every bootstrapper exactly as it was.

BOOTSTRAP_DB_FILE = "/etc/astronomer/secrets/BOOTSTRAP_DB"
DB_BOOTSTRAPPER_VOLUME = "db-bootstrapper-secret"

# Every bootstrapper the chart renders with FlightDeck and laminar on. The CP-HA-only
# houston-cp-refresh hook is covered by its own test.
DB_BOOTSTRAPPER_CONTAINERS = {
    ("release-name-commander", "flightdeck-bootstrapper"),
    ("release-name-houston", "houston-bootstrapper"),
    ("release-name-houston-worker", "houston-bootstrapper"),
    ("release-name-houston-db-migrations", "houston-bootstrapper"),
    ("release-name-houston-upgrade-deployments", "houston-bootstrapper"),
    ("release-name-grafana", "bootstrapper"),
    ("release-name-api-server", "laminar-bootstrapper"),
    ("release-name-hypervisor", "laminar-bootstrapper"),
}

CP_REFRESH_GLOBAL = {
    "plane": {"mode": "control"},
    "controlPlaneHA": {
        "enabled": True,
        "globalBaseDomain": "astro.example.com",
        "cpId": "00000000-0000-0000-0000-000000000001",
    },
}


def db_bootstrapper_values(sff=None, bootstrapper=None, **global_values):
    """Unified install with every bootstrapper rendered. None leaves a toggle at its default."""
    values = {
        "global": {"plane": {"mode": "unified"}, "laminar": {"enabled": True}, **global_values},
        "astronomer": {"flightDeck": {"enabled": True}},
        "laminar": {"imagePullSecrets": [{"name": "quay-pull-secret"}]},
    }
    if sff is not None:
        values["global"]["secretsFromFiles"] = {"enabled": sff}
    if bootstrapper is not None:
        values["global"]["dbBootstrapper"] = {"secretsFromFiles": {"enabled": bootstrapper}}
    return values


def bootstrap_db_consumers(docs):
    """(workload, container, pod_spec) for every container that reads BOOTSTRAP_DB either way."""
    for name, spec in pod_specs(docs):
        for container in all_containers(spec):
            env_vars = get_env_vars_dict(container.get("env") or [])
            if "BOOTSTRAP_DB" in env_vars or "BOOTSTRAP_DB_FILE" in env_vars:
                yield name, container, spec


class TestDbBootstrapperSecretsFromFiles:
    def test_global_flag_alone_leaves_every_bootstrapper_on_the_env_var(self):
        """The explicit-false default is what keeps a loader-less image working.

        With it inherited instead, turning the platform flag on would drop BOOTSTRAP_DB
        from the environment of an image that cannot read the file, and every
        bootstrapper -- and so every pod behind it -- would fail on a missing option.
        """
        docs = render_chart(kube_version=newest_supported_kube_version, values=db_bootstrapper_values(sff=True))

        found = set()
        for name, container, spec in bootstrap_db_consumers(docs):
            found.add((name, container["name"]))
            env_vars = get_env_vars_dict(container["env"])
            assert env_vars["BOOTSTRAP_DB"] == {"secretKeyRef": {"name": "astronomer-bootstrap", "key": "connection"}}
            assert "DB_BOOTSTRAPPER_SECRETS_FROM_FILES" not in env_vars
            assert "BOOTSTRAP_DB_FILE" not in env_vars
            assert DB_BOOTSTRAPPER_VOLUME not in {v["name"] for v in spec.get("volumes") or []}
        assert found == DB_BOOTSTRAPPER_CONTAINERS

    def test_enabled_reads_bootstrap_db_from_a_file_everywhere(self):
        docs = render_chart(kube_version=newest_supported_kube_version, values=db_bootstrapper_values(bootstrapper=True))

        found = set()
        for name, container, spec in bootstrap_db_consumers(docs):
            found.add((name, container["name"]))
            where = f"{name}/{container['name']}"
            env_vars = get_env_vars_dict(container["env"])

            # The value is gone from the pod spec; only the gate and the path remain.
            assert "BOOTSTRAP_DB" not in env_vars, where
            assert env_vars["DB_BOOTSTRAPPER_SECRETS_FROM_FILES"] == "true", where
            assert env_vars["BOOTSTRAP_DB_FILE"] == BOOTSTRAP_DB_FILE, where

            mount = next(m for m in container["volumeMounts"] if m["name"] == DB_BOOTSTRAPPER_VOLUME)
            assert mount["mountPath"] == "/etc/astronomer/secrets", where
            assert mount["readOnly"] is True, where

            volume = next(v for v in spec["volumes"] if v["name"] == DB_BOOTSTRAPPER_VOLUME)
            assert volume["secret"] == {
                "secretName": "astronomer-bootstrap",
                "defaultMode": SECRET_FILE_MODE,
                "items": [{"key": "connection", "path": "BOOTSTRAP_DB"}],
            }, where

            # 0440 is root-owned and the bootstrapper runs as non-root: only the
            # pod's fsGroup lets it open the file, and the loader fails closed if not.
            assert (spec.get("securityContext") or {}).get("fsGroup") is not None, f"{where} has no fsGroup"
        assert found == DB_BOOTSTRAPPER_CONTAINERS

    def test_cp_refresh_hook_bootstrapper_reads_from_a_file(self):
        """houston-cp-refresh only renders with controlPlaneHA on, so the sweep above misses it."""
        values = {"global": {**CP_REFRESH_GLOBAL, "dbBootstrapper": {"secretsFromFiles": {"enabled": True}}}}
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=values,
            show_only=["charts/astronomer/templates/houston/helm-hooks/houston-cp-refresh-job.yaml"],
        )
        spec = docs[0]["spec"]["template"]["spec"]
        bootstrapper = get_containers_by_name(docs[0], include_init_containers=True)["houston-bootstrapper"]

        env_vars = get_env_vars_dict(bootstrapper["env"])
        assert "BOOTSTRAP_DB" not in env_vars
        assert env_vars["BOOTSTRAP_DB_FILE"] == BOOTSTRAP_DB_FILE
        assert DB_BOOTSTRAPPER_VOLUME in {m["name"] for m in bootstrapper["volumeMounts"]}
        assert DB_BOOTSTRAPPER_VOLUME in {v["name"] for v in spec["volumes"]}
        assert spec["securityContext"]["fsGroup"] == 1000

    @pytest.mark.parametrize(
        "workload,extra",
        [
            ("release-name-houston", {"astronomer": {"houston": {"backendSecretName": "my-houston-db"}}}),
            ("release-name-houston-worker", {"astronomer": {"houston": {"backendSecretName": "my-houston-db"}}}),
            ("release-name-houston-db-migrations", {"astronomer": {"houston": {"backendSecretName": "my-houston-db"}}}),
            ("release-name-houston-upgrade-deployments", {"astronomer": {"houston": {"backendSecretName": "my-houston-db"}}}),
            ("release-name-grafana", {"grafana": {"backendSecretName": "my-grafana-db"}}),
            ("release-name-api-server", {"laminar": {"databaseBootstrapper": {"backendSecretName": "my-laminar-db"}}}),
            ("release-name-hypervisor", {"laminar": {"databaseBootstrapper": {"backendSecretName": "my-laminar-db"}}}),
            ("release-name-commander", {"astronomer": {"flightDeck": {"enabled": False}}}),
        ],
    )
    def test_no_volume_when_the_bootstrapper_is_skipped(self, workload, extra):
        """kubelet mounts every pod volume whether or not a container uses it.

        When the operator supplies the backend secret, the bootstrapper is skipped and
        `astronomer-bootstrap` need not exist -- so a leftover volume naming it would
        leave the pod stuck on FailedMount, a regression for exactly the operators
        who opted out of the bootstrapper.
        """
        values = db_bootstrapper_values(bootstrapper=True)
        for key, value in extra.items():
            values[key] = {**values.get(key, {}), **value}
        docs = render_chart(kube_version=newest_supported_kube_version, values=values)

        spec = dict(pod_specs(docs))[workload]
        assert not any("BOOTSTRAP_DB" in str(c.get("env")) for c in all_containers(spec)), f"{workload} still runs a bootstrapper"
        assert DB_BOOTSTRAPPER_VOLUME not in {v["name"] for v in spec.get("volumes") or []}

    def test_bootstrapper_gets_an_fsgroup_even_when_its_component_reads_env_vars(self):
        """The two toggles are independent, so the fsGroup must follow either one.

        Without it the bootstrapper's 0440 file is unreadable in a pod whose own
        component has not opted in, and the loader fails closed.
        """
        values = db_bootstrapper_values(sff=False, bootstrapper=True)
        docs = render_chart(kube_version=newest_supported_kube_version, values=values)
        specs = dict(pod_specs(docs))

        for name, _container in DB_BOOTSTRAPPER_CONTAINERS:
            assert (specs[name].get("securityContext") or {}).get("fsGroup") is not None, name

        # And houston itself is untouched: still on env vars, no houston volume.
        deployment = next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "release-name-houston")
        houston = get_containers_by_name(deployment)["houston"]
        assert "secretKeyRef" in get_env_vars_dict(houston["env"])["DATABASE__CONNECTION"]
        assert "houston-secrets" not in {v["name"] for v in specs["release-name-houston"]["volumes"]}

    def test_no_fsgroup_on_openshift(self):
        """OpenShift assigns an fsGroup from the namespace's SCC range; never hardcode one."""
        values = db_bootstrapper_values(bootstrapper=True, openshift={"enabled": True})
        docs = render_chart(kube_version=newest_supported_kube_version, values=values)
        for name, spec in pod_specs(docs):
            if any(v["name"] == DB_BOOTSTRAPPER_VOLUME for v in spec.get("volumes") or []):
                assert (spec.get("securityContext") or {}).get("fsGroup") is None, name


@pytest.mark.parametrize(
    "global_enabled,component_enabled,expected",
    [
        (None, None, False),
        (True, None, False),  # the explicit-false default holds the image back
        (True, False, False),
        (True, True, True),
        (False, True, True),
        (None, True, True),
    ],
)
def test_db_bootstrapper_toggle_override_precedence(global_enabled, component_enabled, expected):
    """global.dbBootstrapper.secretsFromFiles.enabled overrides global.secretsFromFiles.enabled."""
    values = {"global": {"plane": {"mode": "unified"}}}
    if global_enabled is not None:
        values["global"]["secretsFromFiles"] = {"enabled": global_enabled}
    if component_enabled is not None:
        values["global"]["dbBootstrapper"] = db_bootstrapper_toggle(component_enabled)

    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=values,
        show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
    )
    bootstrapper = get_containers_by_name(docs[0], include_init_containers=True)["houston-bootstrapper"]
    env_vars = get_env_vars_dict(bootstrapper["env"])
    assert (env_vars.get("DB_BOOTSTRAPPER_SECRETS_FROM_FILES") == "true") is expected
    assert ("BOOTSTRAP_DB" in env_vars) is not expected


def test_db_bootstrapper_null_override_does_not_inherit():
    """Pins a Helm behaviour the values.yaml comment depends on.

    A null in user values normally deletes a chart default, but Helm keeps the default
    for a null under `global`. So an operator cannot opt the bootstrapper into the
    platform-wide flag by setting it to ~; they have to set it to true. The default
    itself becomes ~ in values.yaml once a loader-bearing image is pinned, which does
    inherit. If Helm ever starts honouring the null, this fails and the comment can
    offer ~ as an option.
    """
    values = {
        "global": {
            "plane": {"mode": "unified"},
            "secretsFromFiles": {"enabled": True},
            "dbBootstrapper": db_bootstrapper_toggle(None),
        }
    }
    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=values,
        show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
    )
    bootstrapper = get_containers_by_name(docs[0], include_init_containers=True)["houston-bootstrapper"]
    assert "BOOTSTRAP_DB" in get_env_vars_dict(bootstrapper["env"])


# ── Strict secrets-from-files: the mirrored managed-name lists ─────────────────
#
# A component that is on runs a loader that refuses to start if a secret it manages
# is also in its environment. The chart refuses values that would put one there, so
# it needs each loader's list. These are deliberate mirrors, like
# COMMANDER_SECRET_ENV_VARS above: the repositories cannot read each other in CI.

# Must match SECRET_ENV_VARS in astronomer/houston-api src/lib/secrets-from-files/index.ts,
# and secretsFromFiles.houstonSecretEnvVars in templates/_helpers.tpl. The loader also
# manages every name in HOUSTON_SECRETS_FROM_FILES_EXTRA, which the chart builds.
HOUSTON_MANAGED_SECRET_ENV_VARS = {
    "PRISMA__SECRET",
    "DATABASE__CONNECTION",
    "DATABASE_URL",
    "DEPLOYMENTS__DATABASE__CONNECTION",
    "AUTH__OPENID_CONNECT__AUTH0__CLIENT_SECRET",
    "AUTH__OPENID_CONNECT__GOOGLE__CLIENT_SECRET",
    "AUTH__OPENID_CONNECT__OKTA__CLIENT_SECRET",
    "AUTH__OPENID_CONNECT__MICROSOFT__CLIENT_SECRET",
    "AUTH__OPENID_CONNECT__CUSTOM__CLIENT_SECRET",
    "AUTH__OPENID_CONNECT__ADFS__CLIENT_SECRET",
    "AUTH__OPENID_CONNECT_PROVIDERS",
    "SCIM_AUTH_CODE_OKTA",
    "SCIM_AUTH_CODE_MICROSOFT",
    "AUTH__LDAP__BIND_CREDENTIALS",
    "JWT__PASSPHRASE",
    "REGISTRY__AUTH_HEADER",
    "HELM__REGISTRY_AUTH_SECRET",
    "EMAIL__SMTP_URL",
    "EMAIL__SMTP__AUTH__USER",
    "EMAIL__SMTP__AUTH__PASS",
    "APOLLO_KEY",
}

# The other two loaders each manage one name. kuiper matches it case-insensitively,
# because pydantic reads its settings that way.
KUIPER_MANAGED_SECRET_ENV_VARS = {"DATABASE_URL"}
DB_BOOTSTRAPPER_MANAGED_SECRET_ENV_VARS = {"BOOTSTRAP_DB"}

HELPERS_TPL = Path(git_root_dir) / "templates" / "_helpers.tpl"


def helper_names(define_name):
    """The names a list-rendering define in templates/_helpers.tpl renders, in order."""
    text = HELPERS_TPL.read_text()
    body = text.split(f'{{{{- define "{define_name}" -}}}}', 1)[1].split("{{- end }}", 1)[0]
    return re.findall(r'"([A-Z0-9_]+)"', body)


@pytest.mark.parametrize(
    "define_name,mirror,count",
    [
        ("secretsFromFiles.houstonSecretEnvVars", HOUSTON_MANAGED_SECRET_ENV_VARS, 21),
        ("secretsFromFiles.commanderSecretEnvVars", COMMANDER_SECRET_ENV_VARS, 2),
    ],
    ids=["houston", "commander"],
)
def test_the_chart_mirrors_each_loaders_managed_names(define_name, mirror, count):
    """The drift guard for the guard. A name missing from the chart's list is one the
    chart lets through into a component's env, and the loader then refuses to start
    on it; an extra name refuses values the loader would have accepted."""
    names = helper_names(define_name)
    assert len(names) == len(set(names)), f"{define_name} lists a name twice: {names}"
    assert set(names) == mirror
    assert len(names) == count, f"{define_name} should list the loader's {count} names, lists {len(names)}"


@pytest.mark.parametrize("name", helper_names("secretsFromFiles.houstonSecretEnvVars"))
def test_houston_env_refuses_every_managed_name(name):
    """Every name in the chart's own list really is refused, one render each; the test
    above pins that list to the loader's."""
    values = with_secrets_from_files(houston={"env": [{"name": name, "value": SECRET_MARKER}]})
    stderr = render_failure(values, [HOUSTON_API_TEMPLATE])
    assert f"secret-in-environment: astronomer.houston.env sets {name}," in stderr
    assert SECRET_MARKER not in stderr


@pytest.mark.parametrize("name", sorted(COMMANDER_SECRET_ENV_VARS))
@pytest.mark.parametrize("component", ["commander", "pilot"])
def test_commander_loaders_refuse_both_managed_names(component, name):
    """pilot runs commander's loader, which refuses both names whatever the subcommand,
    so pilot.env is held to both even though pilot only reads the FlightDeck DSN."""
    values = merge_values(
        {
            "global": {"plane": {"mode": "data"}, "secretsFromFiles": {"enabled": True}},
            "astronomer": {"flightDeck": {"enabled": True}, "pilot": {"enabled": True}},
        },
        {"astronomer": {component: {"env": [{"name": name, "value": SECRET_MARKER}]}}},
    )
    stderr = render_failure(values, [COMMANDER_TEMPLATE if component == "commander" else PILOT_TEMPLATE])
    assert f"secret-in-environment: astronomer.{component}.env sets {name}," in stderr
    assert SECRET_MARKER not in stderr


# ── Strict: the render-time guard on the operators' env lists ──────────────────

HOUSTON_API_TEMPLATE = "charts/astronomer/templates/houston/api/houston-deployment.yaml"
NAVIGATOR_TEMPLATE = "charts/astronomer/templates/navigator/navigator-deployment.yaml"
DP_LINK_TEMPLATE = "charts/astronomer/templates/dp-link/dp-link-deployment.yaml"
PG_MASTER_TEMPLATE = "charts/postgresql/templates/statefulset.yaml"

# Never a real secret. Asserted absent from every error: messages name variables, not values.
SECRET_MARKER = "sff-never-printed"


def _switch(enabled):
    return {"secretsFromFiles": {"enabled": enabled}}


# Each user env list the guard covers: how to put `env` into it with its component
# on or off (the platform-wide toggle is on either way), where it renders, and names
# its component's loader manages. "raw" lists render verbatim, so a
# valueFrom.secretKeyRef in them would reach the pod spec.
GUARDED_ENV_LISTS = {
    "astronomer.houston.env": {
        "values": lambda env, on: {
            "global": {"secretsFromFiles": {"enabled": True}},
            "astronomer": {"houston": {"env": env, **_switch(on)}},
        },
        "template": HOUSTON_API_TEMPLATE,
        "container": "houston",
        "managed": ("DATABASE_URL",),
        "raw": False,
        "key": "astronomer.houston",
    },
    "astronomer.navigator.env": {
        "values": lambda env, on: {
            "global": {"secretsFromFiles": {"enabled": True}},
            "astronomer": {"navigator": {"enabled": True, "env": env, **_switch(on)}},
        },
        "template": NAVIGATOR_TEMPLATE,
        "container": "navigator",
        "managed": ("DEPLOYMENTS__DATABASE__CONNECTION",),
        "raw": False,
        "key": "astronomer.navigator",
    },
    "astronomer.dpLink.env": {
        "values": lambda env, on: {
            "global": {"plane": {"mode": "control"}, "secretsFromFiles": {"enabled": True}},
            "astronomer": {"dpLink": {"env": env, **_switch(on)}},
        },
        "template": DP_LINK_TEMPLATE,
        "container": "dp-link",
        "managed": ("DATABASE__CONNECTION",),
        "raw": True,
        "key": "astronomer.dpLink",
    },
    "astronomer.commander.env": {
        "values": lambda env, on: {
            "global": {"secretsFromFiles": {"enabled": True}},
            "astronomer": {"commander": {"env": env, **_switch(on)}},
        },
        "template": COMMANDER_TEMPLATE,
        "container": "commander",
        "managed": ("COMMANDER_DATAPLANE_DATABASE_URL", "COMMANDER_FLIGHTDECK_DSN"),
        "raw": False,
        "key": "astronomer.commander",
    },
    "astronomer.pilot.env": {
        "values": lambda env, on: {
            "global": {"plane": {"mode": "data"}, "secretsFromFiles": {"enabled": True}},
            "astronomer": {"flightDeck": {"enabled": True}, "pilot": {"enabled": True, "env": env, **_switch(on)}},
        },
        "template": PILOT_TEMPLATE,
        "container": "pilot",
        "managed": ("COMMANDER_FLIGHTDECK_DSN", "COMMANDER_DATAPLANE_DATABASE_URL"),
        "raw": True,
        "key": "astronomer.pilot",
    },
    "prometheus.filesdReloader.extraEnv": {
        "values": lambda env, on: {
            "global": {"plane": {"mode": "unified"}, "secretsFromFiles": {"enabled": True}},
            "prometheus": {"filesdReloader": {"extraEnv": env, **_switch(on)}},
        },
        "template": FILESD_RELOADER_TEMPLATE,
        "container": "filesd-reloader",
        "managed": ("DATABASE_URL",),
        "raw": True,
        "key": "prometheus.filesdReloader",
    },
    "postgresql.extraEnv": {
        "values": lambda env, on: {
            "global": {"postgresql": {"enabled": True}, "secretsFromFiles": {"enabled": True}},
            "postgresql": {"postgresqlDatabase": "astrodb", "extraEnv": env, **_switch(on)},
        },
        "template": PG_MASTER_TEMPLATE,
        "container": "release-name-postgresql",
        "managed": ("POSTGRES_PASSWORD",),
        "raw": True,
        "key": "postgresql",
    },
    "global.customLogging.extraEnv": {
        "values": lambda env, on: {
            "global": {
                "plane": {"mode": "unified"},
                "secretsFromFiles": {"enabled": True},
                "customLogging": {
                    "enabled": True,
                    "host": "es.example.com",
                    "secretName": "my-es-creds",
                    "extraEnv": env,
                    **_switch(on),
                },
            }
        },
        "template": ESP_TEMPLATES[0],
        "container": "external-es-proxy",
        "managed": ("ES_SECRET", "ES_SECRET_NAME"),
        "raw": True,
        "key": "global.customLogging",
    },
}

RAW_ENV_LISTS = [key for key, case in GUARDED_ENV_LISTS.items() if case["raw"]]
GUARDED_ENV_NAMES = [(key, name) for key, case in GUARDED_ENV_LISTS.items() for name in case["managed"]]


def guarded_env(list_key, env, on):
    """Render one guarded list's template with `env` in the list; returns that container's env."""
    case = GUARDED_ENV_LISTS[list_key]
    docs = render_chart(
        kube_version=newest_supported_kube_version,
        values=case["values"](env, on),
        show_only=[case["template"]],
    )
    doc = next(d for d in docs if d["kind"] in ("Deployment", "StatefulSet"))
    return get_containers_by_name(doc)[case["container"]]["env"]


def guarded_env_failure(list_key, env):
    case = GUARDED_ENV_LISTS[list_key]
    return render_failure(case["values"](env, True), [case["template"]])


@pytest.mark.parametrize("list_key,name", GUARDED_ENV_NAMES)
class TestStrictEnvListGuard:
    def test_a_managed_name_fails_the_render(self, list_key, name):
        case = GUARDED_ENV_LISTS[list_key]
        stderr = guarded_env_failure(list_key, [{"name": name, "value": SECRET_MARKER}])
        assert f"secret-in-environment: {list_key} sets {name}," in stderr
        assert f"set {case['key']}.secretsFromFiles.enabled=false" in stderr
        assert SECRET_MARKER not in stderr

    def test_a_managed_name_from_a_value_from_fails_the_render(self, list_key, name):
        """valueFrom resolves to a value at container start, so it counts too, from
        any source -- whether or not the list renders the valueFrom at all."""
        env = [{"name": name, "valueFrom": {"configMapKeyRef": {"name": "some-config", "key": "k"}}}]
        assert f"{list_key} sets {name}," in guarded_env_failure(list_key, env)

    def test_a_managed_name_renders_with_the_component_off(self, list_key, name):
        """The way out: turned off on its own, the component keeps env-var behaviour,
        including whatever its env list sets."""
        entry = {"name": name, "value": SECRET_MARKER}
        assert entry in guarded_env(list_key, [entry], on=False)

    def test_an_empty_value_is_allowed(self, list_key, name):
        """An empty value holds no secret and is how a variable is blanked; the loaders
        accept it, and so does the chart."""
        env = guarded_env(list_key, [{"name": name, "value": ""}], on=True)
        assert {"name": name, "value": ""} in env


@pytest.mark.parametrize("list_key", list(GUARDED_ENV_LISTS))
def test_an_unmanaged_value_is_allowed(list_key):
    env = guarded_env(list_key, [{"name": "SFF_PLAIN_SETTING", "value": "on"}], on=True)
    assert {"name": "SFF_PLAIN_SETTING", "value": "on"} in env


# How YAML normalises a name: the name/value lists and the secret[] envNames are
# rendered unquoted, so surrounding whitespace and one pair of quotes disappear.
NAME_VARIANTS = {
    "trailing-space": "{} ",
    "leading-space": " {}",
    "single-quoted": "'{}'",
    "double-quoted": '"{}"',
    "quoted-and-padded": " '{}' ",
}


@pytest.mark.parametrize("variant", list(NAME_VARIANTS))
def test_yaml_renders_a_quoted_or_padded_name_as_the_plain_name(variant):
    """Why the guards normalise names: with houston off, the rendered env var is the
    plain name, so comparing raw values would let a variant slip past the guard."""
    name = NAME_VARIANTS[variant].format("SFF_PADDED_SETTING")
    env = guarded_env("astronomer.houston.env", [{"name": name, "value": "x"}], on=False)
    assert {"name": "SFF_PADDED_SETTING", "value": "x"} in env


@pytest.mark.parametrize("variant", list(NAME_VARIANTS))
def test_a_quoted_or_padded_managed_name_is_still_refused(variant):
    name = NAME_VARIANTS[variant].format("DATABASE_URL")
    stderr = guarded_env_failure("astronomer.houston.env", [{"name": name, "value": SECRET_MARKER}])
    assert "secret-in-environment: astronomer.houston.env sets DATABASE_URL," in stderr
    assert SECRET_MARKER not in stderr


@pytest.mark.parametrize("variant", list(NAME_VARIANTS))
def test_a_quoted_or_padded_loader_setting_is_still_refused(variant):
    name = NAME_VARIANTS[variant].format("HOUSTON_SECRETS_FROM_FILES")
    stderr = guarded_env_failure("astronomer.houston.env", [{"name": name, "value": "false"}])
    assert "loader-setting-in-environment: astronomer.houston.env sets HOUSTON_SECRETS_FROM_FILES," in stderr


@pytest.mark.parametrize("variant", list(NAME_VARIANTS))
def test_a_quoted_or_padded_secret_env_name_still_collides(variant):
    secrets = [
        {"envName": "SFF_TOKEN", "secretName": "sff-one"},
        {"envName": NAME_VARIANTS[variant].format("SFF_TOKEN"), "secretName": "sff-two"},
    ]
    stderr = render_failure(secret_list_values("houston", secrets), [HOUSTON_API_TEMPLATE])
    assert (
        "duplicate-secret-name: astronomer.houston.secret[1].envName repeats SFF_TOKEN from astronomer.houston.secret[0]" in stderr
    )


@pytest.mark.parametrize("variant", list(NAME_VARIANTS))
def test_a_quoted_or_padded_secret_env_name_is_still_reserved(variant):
    secrets = [{"envName": NAME_VARIANTS[variant].format("DATABASE_URL"), "secretName": "sff-db"}]
    stderr = render_failure(secret_list_values("houston", secrets), [HOUSTON_API_TEMPLATE])
    assert (
        "duplicate-secret-name: astronomer.houston.secret[0].envName is DATABASE_URL, a secret the chart already delivers" in stderr
    )


# The settings the chart renders for a component's loader -- its gate, houston's
# EXTRA list, a managed name's <VAR>_FILE -- may not be set in its env list either,
# with any value: a later entry overrides the chart's, turning the loader off or
# pointing it somewhere else.
LOADER_SETTINGS = [
    ("astronomer.houston.env", "HOUSTON_SECRETS_FROM_FILES"),
    ("astronomer.houston.env", "HOUSTON_SECRETS_FROM_FILES_EXTRA"),
    ("astronomer.houston.env", "DATABASE_URL_FILE"),
    ("astronomer.houston.env", "REGISTRY__AUTH_HEADER_FILE"),
    ("astronomer.houston.env", "AUTH__LDAP__BIND_CREDENTIALS_FILE"),
    ("astronomer.navigator.env", "HOUSTON_SECRETS_FROM_FILES"),
    ("astronomer.navigator.env", "HOUSTON_SECRETS_FROM_FILES_EXTRA"),
    ("astronomer.navigator.env", "DEPLOYMENTS__DATABASE__CONNECTION_FILE"),
    ("astronomer.dpLink.env", "HOUSTON_SECRETS_FROM_FILES"),
    ("astronomer.dpLink.env", "HOUSTON_SECRETS_FROM_FILES_EXTRA"),
    ("astronomer.dpLink.env", "DATABASE__CONNECTION_FILE"),
    ("astronomer.commander.env", "COMMANDER_SECRETS_FROM_FILES"),
    ("astronomer.commander.env", "COMMANDER_FLIGHTDECK_DSN_FILE"),
    ("astronomer.pilot.env", "COMMANDER_SECRETS_FROM_FILES"),
    ("astronomer.pilot.env", "COMMANDER_DATAPLANE_DATABASE_URL_FILE"),
    ("prometheus.filesdReloader.extraEnv", "KUIPER_SECRETS_FROM_FILES"),
    ("prometheus.filesdReloader.extraEnv", "database_url_file"),
]


@pytest.mark.parametrize("list_key,name", LOADER_SETTINGS)
class TestStrictLoaderSettingGuard:
    @pytest.mark.parametrize("value", ["/custom/path", ""], ids=["value", "empty"])
    def test_a_loader_setting_fails_the_render(self, list_key, name, value):
        case = GUARDED_ENV_LISTS[list_key]
        stderr = guarded_env_failure(list_key, [{"name": name, "value": value}])
        assert f"loader-setting-in-environment: {list_key} sets {name}," in stderr
        assert f"set {case['key']}.secretsFromFiles.enabled=false" in stderr

    def test_a_loader_setting_renders_with_the_component_off(self, list_key, name):
        entry = {"name": name, "value": "/custom/path"}
        assert entry in guarded_env(list_key, [entry], on=False)


@pytest.mark.parametrize(
    "name,hint",
    [("AUTH__LDAP__BIND_CREDENTIALS_FILE", True), ("DATABASE_URL_FILE", False), ("REGISTRY__AUTH_HEADER_FILE", False)],
    ids=["operator-secret", "chart-delivered", "chart-delivered-api-only"],
)
def test_a_secret_file_setting_points_at_the_secret_list_when_it_can(name, hint):
    """houston, navigator and dp-link take extra secrets as files through secret[], so
    that is the fix offered for a <VAR>_FILE set by hand -- but not for a secret the
    chart delivers itself, which secret[] may not name."""
    stderr = guarded_env_failure("astronomer.houston.env", [{"name": name, "value": "/x"}])
    assert f"loader-setting-in-environment: astronomer.houston.env sets {name}," in stderr
    assert ("and deliver the secret as a file through astronomer.houston.secret instead" in stderr) is hint


SECRET_KEY_REF_ENTRY = {"name": "SFF_EXTRA_TOKEN", "valueFrom": {"secretKeyRef": {"name": "sff-extra", "key": "token"}}}


@pytest.mark.parametrize("list_key", RAW_ENV_LISTS)
class TestStrictRawEnvListGuard:
    def test_any_secret_key_ref_fails_the_render(self, list_key):
        """A component that is on takes no secret from its environment, managed or not."""
        case = GUARDED_ENV_LISTS[list_key]
        stderr = guarded_env_failure(list_key, [SECRET_KEY_REF_ENTRY])
        assert f"secret-in-environment: {list_key} takes SFF_EXTRA_TOKEN from a secretKeyRef" in stderr
        assert f"set {case['key']}.secretsFromFiles.enabled=false" in stderr

    def test_a_secret_key_ref_renders_with_the_component_off(self, list_key):
        env = guarded_env(list_key, [SECRET_KEY_REF_ENTRY], on=False)
        assert SECRET_KEY_REF_ENTRY in env

    def test_other_value_froms_are_allowed(self, list_key):
        entry = {"name": "SFF_POD_NAME", "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}}}
        assert entry in guarded_env(list_key, [entry], on=True)


def test_dp_link_points_secret_key_refs_at_its_secret_list():
    """dp-link can take extra secrets as files, so the fix offered is that, not removal."""
    stderr = guarded_env_failure("astronomer.dpLink.env", [SECRET_KEY_REF_ENTRY])
    assert "Deliver SFF_EXTRA_TOKEN as a file through astronomer.dpLink.secret instead" in stderr


@pytest.mark.parametrize("name", ["database_url", "Database_Url"])
def test_filesd_reloader_refuses_database_url_in_any_case(name):
    """pydantic reads its settings case-insensitively, so kuiper's loader refuses a
    lowercase database_url as well, and so must the chart."""
    stderr = guarded_env_failure("prometheus.filesdReloader.extraEnv", [{"name": name, "value": SECRET_MARKER}])
    assert f"prometheus.filesdReloader.extraEnv sets {name}," in stderr


def test_filesd_reloader_extra_env_is_not_checked_where_the_sidecar_does_not_run():
    """The sidecar only renders on a control-capable plane."""
    values = GUARDED_ENV_LISTS["prometheus.filesdReloader.extraEnv"]["values"]([{"name": "DATABASE_URL", "value": "x"}], True)
    values["global"]["plane"] = {"mode": "data"}
    docs = render_chart(kube_version=newest_supported_kube_version, values=values, show_only=[FILESD_RELOADER_TEMPLATE])
    assert "filesd-reloader" not in get_containers_by_name(docs[0])


HOUSTON_FAMILY = {
    "houston": (HOUSTON_API_TEMPLATE, "houston"),
    "navigator": (NAVIGATOR_TEMPLATE, "navigator"),
    "dpLink": (DP_LINK_TEMPLATE, "dp-link"),
}


@pytest.mark.parametrize("component", list(HOUSTON_FAMILY))
class TestHoustonFamilyOwnNames:
    """Each component's EXTRA list -- its secret[] envNames, and CP_ID under
    controlPlaneHA -- is managed by its loader as well, so those names and their
    <NAME>_FILE are refused in its own env list."""

    def test_its_secret_env_names_are_managed_too(self, component):
        values = secret_list_values(component, [{"envName": "SFF_OPERATOR_TOKEN", "secretName": "sff-op"}])
        values["astronomer"][component]["env"] = [{"name": "SFF_OPERATOR_TOKEN", "value": SECRET_MARKER}]
        stderr = render_failure(values, [HOUSTON_FAMILY[component][0]])
        assert f"secret-in-environment: astronomer.{component}.env sets SFF_OPERATOR_TOKEN," in stderr

    def test_its_secret_files_are_loader_settings(self, component):
        values = secret_list_values(component, [{"envName": "SFF_OPERATOR_TOKEN", "secretName": "sff-op"}])
        values["astronomer"][component]["env"] = [{"name": "SFF_OPERATOR_TOKEN_FILE", "value": "/x"}]
        stderr = render_failure(values, [HOUSTON_FAMILY[component][0]])
        assert f"loader-setting-in-environment: astronomer.{component}.env sets SFF_OPERATOR_TOKEN_FILE," in stderr

    @pytest.mark.parametrize("name", ["CP_ID", "CP_ID_FILE"])
    def test_cp_id_is_refused_under_ha(self, component, name):
        """Under controlPlaneHA, CP_ID arrives as a file and is in EXTRA, so the loader
        refuses it, and the chart its file setting, in the environment."""
        values = secret_list_values(component, [], ha=True)
        values["astronomer"][component]["env"] = [{"name": name, "value": "cp-a"}]
        stderr = render_failure(values, [HOUSTON_FAMILY[component][0]])
        assert f"astronomer.{component}.env sets {name}," in stderr

    @pytest.mark.parametrize("name", ["CP_ID", "CP_ID_FILE"])
    def test_cp_id_is_left_alone_without_ha(self, component, name):
        """Without HA the chart does not deliver CP_ID at all, so the loader does not
        manage it and an operator value is left alone."""
        template, container = HOUSTON_FAMILY[component]
        values = secret_list_values(component, [])
        values["astronomer"][component]["env"] = [{"name": name, "value": "cp-a"}]
        docs = render_chart(kube_version=newest_supported_kube_version, values=values, show_only=[template])
        assert {"name": name, "value": "cp-a"} in get_containers_by_name(docs[0])[container]["env"]


# ── Strict: operator secret[] entries may not collide ──────────────────────────

SECRET_LIST_COMPONENTS = {
    "houston": {"template": HOUSTON_API_TEMPLATE, "chart_file": "DATABASE_URL", "extra": {}},
    "navigator": {"template": NAVIGATOR_TEMPLATE, "chart_file": "DATABASE_URL", "extra": {"enabled": True}},
    "dpLink": {"template": DP_LINK_TEMPLATE, "chart_file": "DATABASE__CONNECTION", "extra": {}},
}


def secret_list_values(component, secrets, on=True, ha=False):
    values = {
        "global": {"plane": {"mode": "control"}, "secretsFromFiles": {"enabled": True}},
        "astronomer": {component: {"secret": secrets, **SECRET_LIST_COMPONENTS[component]["extra"], **_switch(on)}},
    }
    if ha:
        values["global"]["controlPlaneHA"] = {
            "enabled": True,
            "globalBaseDomain": "astro.example.com",
            "cpId": "00000000-0000-0000-0000-000000000001",
        }
    return values


DUPLICATE_SECRETS = [
    {"envName": "SFF_TOKEN", "secretName": "sff-one"},
    {"envName": "SFF_TOKEN", "secretName": "sff-two"},
]


@pytest.mark.parametrize("component", list(SECRET_LIST_COMPONENTS))
class TestStrictSecretListCollisions:
    """Each secret[] entry becomes a file named after its envName in the component's
    projected volume. Two sources for one path make the API server reject the whole
    volume at apply time, so the chart refuses it at render while the component is on."""

    def test_a_repeated_env_name_fails_the_render(self, component):
        template = SECRET_LIST_COMPONENTS[component]["template"]
        stderr = render_failure(secret_list_values(component, DUPLICATE_SECRETS), [template])
        assert (
            f"duplicate-secret-name: astronomer.{component}.secret[1].envName repeats SFF_TOKEN from astronomer.{component}.secret[0]"
            in stderr
        )
        assert f"set astronomer.{component}.secretsFromFiles.enabled=false" in stderr

    def test_a_repeated_env_name_renders_with_the_component_off(self, component):
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=secret_list_values(component, DUPLICATE_SECRETS, on=False),
            show_only=[SECRET_LIST_COMPONENTS[component]["template"]],
        )
        assert docs, "off, the entries are plain secretKeyRef env vars and render as before"

    def test_a_file_the_chart_projects_fails_the_render(self, component):
        chart_file = SECRET_LIST_COMPONENTS[component]["chart_file"]
        secrets = [{"envName": chart_file, "secretName": "sff-db"}]
        stderr = render_failure(secret_list_values(component, secrets), [SECRET_LIST_COMPONENTS[component]["template"]])
        assert (
            f"duplicate-secret-name: astronomer.{component}.secret[0].envName is {chart_file}, a secret the chart already delivers"
            in stderr
        )

    def test_cp_id_is_reserved_under_ha(self, component):
        secrets = [{"envName": "CP_ID", "secretName": "sff-cp"}]
        template = SECRET_LIST_COMPONENTS[component]["template"]
        stderr = render_failure(secret_list_values(component, secrets, ha=True), [template])
        assert (
            f"duplicate-secret-name: astronomer.{component}.secret[0].envName is CP_ID, a secret the chart already delivers"
            in stderr
        )

    def test_cp_id_is_an_ordinary_name_without_ha(self, component):
        """Without controlPlaneHA the chart projects no CP_ID, so nothing collides."""
        secrets = [{"envName": "CP_ID", "secretName": "sff-cp"}]
        template = SECRET_LIST_COMPONENTS[component]["template"]
        docs = render_chart(
            kube_version=newest_supported_kube_version, values=secret_list_values(component, secrets), show_only=[template]
        )
        sources = next(
            v["projected"]["sources"] for v in docs[0]["spec"]["template"]["spec"]["volumes"] if v["name"].endswith("-secrets")
        )
        assert {"secret": {"name": "sff-cp", "items": [{"key": "value", "path": "CP_ID"}]}} in sources

    def test_an_entry_needs_an_env_name(self, component):
        stderr = render_failure(
            secret_list_values(component, [{"secretName": "sff-nameless"}]), [SECRET_LIST_COMPONENTS[component]["template"]]
        )
        assert f"invalid-secret-entry: astronomer.{component}.secret[0] has no envName" in stderr

    def test_deployments_connection_is_reserved_while_the_chart_delivers_it(self, component):
        secrets = [{"envName": "DEPLOYMENTS__DATABASE__CONNECTION", "secretName": "sff-db"}]
        stderr = render_failure(secret_list_values(component, secrets), [SECRET_LIST_COMPONENTS[component]["template"]])
        assert "envName is DEPLOYMENTS__DATABASE__CONNECTION, a secret the chart already delivers" in stderr

    def test_deployments_connection_is_free_when_set_inline(self, component):
        """With houston.config.deployments.database.connection set inline the chart
        delivers no DEPLOYMENTS__DATABASE__CONNECTION, so an operator entry is the only one."""
        values = secret_list_values(component, [{"envName": "DEPLOYMENTS__DATABASE__CONNECTION", "secretName": "sff-db"}])
        values["astronomer"].setdefault("houston", {})["config"] = {
            "deployments": {"database": {"connection": {"host": "inline-host"}}}
        }
        docs = render_chart(
            kube_version=newest_supported_kube_version, values=values, show_only=[SECRET_LIST_COMPONENTS[component]["template"]]
        )
        volume = next(v for v in docs[0]["spec"]["template"]["spec"]["volumes"] if v["name"].endswith("-secrets"))
        paths = [item["path"] for source in volume["projected"]["sources"] for item in source["secret"]["items"]]
        assert paths.count("DEPLOYMENTS__DATABASE__CONNECTION") == 1


@pytest.mark.parametrize("component,reserved", [("houston", True), ("navigator", False), ("dpLink", False)])
def test_registry_auth_header_is_reserved_where_the_chart_delivers_it(component, reserved):
    """The chart delivers REGISTRY__AUTH_HEADER to the houston API from its own volume,
    so a houston.secret[] copy would give that container two REGISTRY__AUTH_HEADER_FILE
    paths; navigator and dp-link never get it, so for them it is an ordinary name."""
    values = secret_list_values(component, [{"envName": "REGISTRY__AUTH_HEADER", "secretName": "sff-registry"}])
    template = SECRET_LIST_COMPONENTS[component]["template"]
    if reserved:
        stderr = render_failure(values, [template])
        assert (
            "duplicate-secret-name: astronomer.houston.secret[0].envName is REGISTRY__AUTH_HEADER, a secret the chart already delivers"
            in stderr
        )
    else:
        assert render_chart(kube_version=newest_supported_kube_version, values=values, show_only=[template])


# ── Strict: the switches must be booleans ──────────────────────────────────────
#
# Turning one component off is the way out of strict mode, so a switch that fails
# open is worse than useless. A quoted "false" is a string: read as unset, it let a
# global true turn the component on anyway.

# values path -> (values setting that switch to a value, a template it affects, a
# container there, and an env var that container has only while the switch is on)
TOGGLE_CASES = {
    "astronomer.houston": (
        lambda v: {"astronomer": {"houston": _switch(v)}},
        HOUSTON_API_TEMPLATE,
        "houston",
        "HOUSTON_SECRETS_FROM_FILES",
    ),
    "astronomer.navigator": (
        lambda v: {"astronomer": {"navigator": {"enabled": True, **_switch(v)}}},
        NAVIGATOR_TEMPLATE,
        "navigator",
        "HOUSTON_SECRETS_FROM_FILES",
    ),
    "astronomer.commander": (
        lambda v: {"astronomer": {"commander": _switch(v)}},
        COMMANDER_TEMPLATE,
        "commander",
        "COMMANDER_SECRETS_FROM_FILES",
    ),
    "prometheus.filesdReloader": (
        lambda v: {"prometheus": {"filesdReloader": _switch(v)}},
        FILESD_RELOADER_TEMPLATE,
        "filesd-reloader",
        "KUIPER_SECRETS_FROM_FILES",
    ),
    "postgresql": (
        lambda v: {"global": {"postgresql": {"enabled": True}}, "postgresql": _switch(v)},
        PG_MASTER_TEMPLATE,
        "release-name-postgresql",
        "POSTGRES_PASSWORD_FILE",
    ),
    "global.dbBootstrapper": (
        lambda v: {"global": {"dbBootstrapper": _switch(v)}},
        HOUSTON_API_TEMPLATE,
        "houston-bootstrapper",
        "DB_BOOTSTRAPPER_SECRETS_FROM_FILES",
    ),
}


def toggle_values(key, value):
    """The platform-wide toggle on, and one component's switch set to value."""
    base = {"global": {"plane": {"mode": "unified"}, "secretsFromFiles": {"enabled": True}}}
    return merge_values(base, TOGGLE_CASES[key][0](value))


@pytest.mark.parametrize("key", list(TOGGLE_CASES))
def test_a_string_toggle_fails_the_render(key):
    stderr = render_failure(toggle_values(key, "false"), [TOGGLE_CASES[key][1]])
    assert f'invalid-gate-value: {key}.secretsFromFiles.enabled is set to "false" (type string), not a boolean' in stderr
    if key == "global.dbBootstrapper":
        # Its default is an explicit false, which Helm keeps for a null under
        # global, so "leave it unset to inherit" would be bad advice there.
        assert "leave it unset" not in stderr
        assert "A null here does not inherit global.secretsFromFiles.enabled" in stderr
    else:
        assert "or leave it unset (null) to inherit global.secretsFromFiles.enabled" in stderr


@pytest.mark.parametrize("value", [True, False], ids=["true", "false"])
@pytest.mark.parametrize("key", list(TOGGLE_CASES))
def test_a_boolean_switch_is_honoured(key, value):
    """A real boolean renders, and decides: with the platform-wide toggle on, true
    keeps the component on and false turns it off. For global.dbBootstrapper, whose
    default is false, it is the true case that shows the switch takes effect."""
    _values, template, container, file_only_env = TOGGLE_CASES[key]
    docs = render_chart(kube_version=newest_supported_kube_version, values=toggle_values(key, value), show_only=[template])
    doc = next(d for d in docs if d["kind"] in ("Deployment", "StatefulSet"))
    env_vars = get_env_vars_dict(get_containers_by_name(doc, include_init_containers=True)[container]["env"])
    assert (file_only_env in env_vars) is value


@pytest.mark.parametrize("value", ["true", "on", 1], ids=["quoted-true", "on", "integer"])
def test_a_non_boolean_global_toggle_fails_the_render(value):
    stderr = render_failure({"global": {"secretsFromFiles": {"enabled": value}}}, [HOUSTON_API_TEMPLATE])
    assert "invalid-gate-value: global.secretsFromFiles.enabled is set to" in stderr
    assert "not a boolean" in stderr
    # Nothing to inherit from: this is the platform-wide default.
    assert "inherit" not in stderr


def test_a_null_toggle_inherits():
    values = toggle_values("astronomer.houston", None)
    docs = render_chart(kube_version=newest_supported_kube_version, values=values, show_only=[HOUSTON_API_TEMPLATE])
    assert get_env_vars_dict(get_containers_by_name(docs[0])["houston"]["env"])["HOUSTON_SECRETS_FROM_FILES"] == "true"


# ── Strict: CP_ID arrives as a file under controlPlaneHA ───────────────────────

CP_ID_COMPONENTS = {
    "houston": (HOUSTON_API_TEMPLATE, "houston", "houston-secrets"),
    "navigator": (NAVIGATOR_TEMPLATE, "navigator", "navigator-secrets"),
    "dpLink": (DP_LINK_TEMPLATE, "dp-link", "dp-link-secrets"),
}

CP_ID_SOURCE = {"secret": {"name": "cp-identity", "items": [{"key": "cp_id", "path": "CP_ID"}]}}


def cp_id_values(component, on, ha=True):
    values = {
        "global": {
            "plane": {"mode": "control"},
            "secretsFromFiles": {"enabled": True},
            "controlPlaneHA": {
                "enabled": ha,
                "globalBaseDomain": "astro.example.com",
                "cpId": "00000000-0000-0000-0000-000000000001",
            },
        },
        "astronomer": {"navigator": {"enabled": True}},
    }
    return merge_values(values, {"astronomer": {component: _switch(on)}})


def cp_id_render(component, on, ha=True):
    template, container, volume = CP_ID_COMPONENTS[component]
    docs = render_chart(kube_version=newest_supported_kube_version, values=cp_id_values(component, on, ha), show_only=[template])
    spec = docs[0]["spec"]["template"]["spec"]
    env = get_containers_by_name(docs[0])[container]["env"]
    sources = next((v["projected"]["sources"] for v in spec["volumes"] if v["name"] == volume), [])
    return get_env_vars_dict(env), sources


@pytest.mark.parametrize("component", list(CP_ID_COMPONENTS))
class TestCpIdFromFiles:
    def test_on_under_ha_cp_id_is_a_file(self, component):
        """The last secretKeyRef in houston-family containers that are on: CP_ID now
        comes from cp-identity through the component's own secret volume, and is in
        EXTRA so the loader requires it and refuses it in the environment."""
        env_vars, sources = cp_id_render(component, on=True)
        assert "CP_ID" not in env_vars
        assert env_vars["CP_ID_FILE"] == "/etc/astronomer/secrets/CP_ID"
        assert "CP_ID" in env_vars["HOUSTON_SECRETS_FROM_FILES_EXTRA"].split(",")
        assert CP_ID_SOURCE in sources

    def test_off_under_ha_cp_id_is_still_a_secret_key_ref(self, component):
        env_vars, sources = cp_id_render(component, on=False)
        assert env_vars["CP_ID"] == {"secretKeyRef": {"name": "cp-identity", "key": "cp_id"}}
        assert "CP_ID_FILE" not in env_vars
        assert sources == []

    def test_on_without_ha_there_is_no_cp_id(self, component):
        env_vars, sources = cp_id_render(component, on=True, ha=False)
        assert "CP_ID" not in env_vars
        assert "CP_ID_FILE" not in env_vars
        assert "CP_ID" not in env_vars.get("HOUSTON_SECRETS_FROM_FILES_EXTRA", "").split(",")
        assert CP_ID_SOURCE not in sources


def test_cp_id_is_a_file_in_every_houston_workload_under_ha():
    """houston_environment and houston_secret_volumes are shared by the API, worker, the
    hooks and every cronjob; each loader container must get CP_ID the same way."""
    values = with_secrets_from_files()
    values["global"] = {**values["global"], **CP_REFRESH_GLOBAL}
    docs = render_chart(kube_version=newest_supported_kube_version, values=values)

    checked = 0
    for name, spec in houston_family_pod_specs(docs):
        for container in spec["containers"]:
            env_vars = get_env_vars_dict(container.get("env") or [])
            if env_vars.get("HOUSTON_SECRETS_FROM_FILES") != "true":
                continue
            checked += 1
            assert "CP_ID" not in env_vars, f"{name}/{container['name']}"
            assert env_vars["CP_ID_FILE"] == "/etc/astronomer/secrets/CP_ID", f"{name}/{container['name']}"
        volume = next((v for v in spec.get("volumes") or [] if v["name"].endswith("-secrets") and "projected" in v), None)
        if volume:
            assert CP_ID_SOURCE in volume["projected"]["sources"], name
    assert checked >= 14, f"only {checked} houston-family loader containers rendered"


# ── Strict: what each container sees is what it advertises ─────────────────────


def test_flightdeck_migrations_see_only_the_flightdeck_dsn():
    """flightdeck-db-migrations advertises only the FlightDeck DSN, and the loader also
    reads any other managed file it finds at the default path -- so with the whole
    commander-secrets volume mounted it loaded the data-plane URL too, unadvertised.
    A subPath of the same volume, which is the one the wait-for-secret gate polls."""
    values = {"global": {"secretsFromFiles": {"enabled": True}}, "astronomer": {"flightDeck": {"enabled": True}}}
    docs = render_chart(kube_version=newest_supported_kube_version, values=values, show_only=[COMMANDER_TEMPLATE])
    containers = get_containers_by_name(docs[0], include_init_containers=True)
    migrations = containers["flightdeck-db-migrations"]

    secret_mounts = [m for m in migrations["volumeMounts"] if m["mountPath"].startswith("/etc/astronomer/secrets")]
    assert secret_mounts == [
        {
            "name": "commander-secrets",
            "mountPath": "/etc/astronomer/secrets/COMMANDER_FLIGHTDECK_DSN",
            "subPath": "COMMANDER_FLIGHTDECK_DSN",
            "readOnly": True,
        }
    ]
    assert {k for k in get_env_vars_dict(migrations["env"]) if k.endswith("_FILE")} == {"COMMANDER_FLIGHTDECK_DSN_FILE"}
    assert containers["wait-for-secret"]["volumeMounts"][0]["name"] == "commander-secrets"


@pytest.mark.parametrize("enabled", [False, True], ids=["dp-link-off", "dp-link-on"])
def test_dp_link_env_keeps_its_deliberate_double_render(enabled):
    """Every release so far rendered each dpLink.env entry twice: name and value in
    dp_link_environment, then verbatim at the end of the container's env, which is
    the copy Kubernetes keeps. Dropping the first copy makes Helm's three-way
    strategic merge patch emit a $patch: delete for the name, which removes BOTH
    copies, so dp-link would restart once without the operator's env. Kept until a
    release renames the dp-link container; change this test in that release."""
    env = [{"name": "SFF_SETTING", "value": "one"}]
    if not enabled:
        env.append(SECRET_KEY_REF_ENTRY)
    values = {
        "global": {"plane": {"mode": "control"}, "secretsFromFiles": {"enabled": True}},
        "astronomer": {"dpLink": {"env": env, **_switch(enabled)}},
    }
    docs = render_chart(kube_version=newest_supported_kube_version, values=values, show_only=[DP_LINK_TEMPLATE])
    dp_link_env = get_containers_by_name(docs[0])["dp-link"]["env"]
    for entry in env:
        copies = [e for e in dp_link_env if e["name"] == entry["name"]]
        assert len(copies) == 2, f"{entry['name']} rendered {len(copies)} times"
        # The verbatim copy comes last, so it is the one Kubernetes keeps.
        assert copies[-1] == entry
        assert copies[0] == {"name": entry["name"], "value": entry.get("value")}


# The volumes a loader reads its secrets from. A gated container's view of these is
# what it can load; it must match what it advertises exactly.
STRICT_LOADER_VOLUMES = LOADER_SECRET_VOLUMES | {"filesd-reloader-secrets"}

# Everything converted turned on at once, so the sweeps below see every gated
# container the chart can render. Feeds the consistency sweep, the residual
# inventory and the per-switch matrix.
STRICT_ALL_ON = {
    "global": {
        "secretsFromFiles": {"enabled": True},
        "dbBootstrapper": db_bootstrapper_toggle(True),
        "metricsReporting": {"taskUsageMetrics": {"enabled": True}},
        "laminar": {"enabled": True},
        "postgresql": {"enabled": True},
        "prometheusPostgresExporter": {"enabled": True},
        "customLogging": {"enabled": True, "host": "es.example.com", "secretName": "my-es-creds", "awsSecretName": "my-aws-creds"},
    },
    "laminar": {"imagePullSecrets": [{"name": "quay-pull-secret"}]},
    "astronomer": {
        **ALL_CRONJOBS,
        "houston": {
            **ALL_CRONJOBS["houston"],
            "secret": [{"envName": "EMAIL__SMTP_URL", "secretName": "my-smtp", "secretKey": "connection"}],
            "logging": {
                "loggingSidecar": {
                    "enabled": True,
                    "elasticsearch": {
                        "enabled": True,
                        "endpoint": "https://es.example.com:9200",
                        "auth": {"strategy": "basic", "secretName": "es-basic"},
                    },
                }
            },
        },
        "flightDeck": {"enabled": True},
        "pilot": {"enabled": True},
        "navigator": {"enabled": True, "secret": [{"envName": "NAV_TOKEN", "secretName": "nav-secret"}]},
        "dpLink": {"enabled": True, "secret": [{"envName": "DPL_TOKEN", "secretName": "dpl-secret"}]},
        "mcpServer": {"enabled": True, "secret": [{"envName": "MCP_TOKEN", "secretName": "mcp-secret"}]},
    },
    "postgresql": {"postgresqlDatabase": "astrodb", "replication": {"enabled": True}, "metrics": {"enabled": True}},
    "prometheus-postgres-exporter": {
        "config": {
            "datasource": {
                "connectionSecret": None,
                "host": "pg.example.com",
                "user": "exporter",
                "passwordSecret": {"name": "my-pg-secret", "key": "my-password-key"},
            }
        }
    },
}

STRICT_PLANES = {
    "unified": {"plane": {"mode": "unified"}},
    "control-ha": CP_REFRESH_GLOBAL,
    "data": {"plane": {"mode": "data", "domainPrefix": "dp01"}},
}


def merge_values(base, override):
    """Deep-merge override into a copy of base."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_values(merged[key], value)
        else:
            merged[key] = value
    return merged


def strict_values(plane, override=None, enabled=True):
    values = merge_values(STRICT_ALL_ON, {"global": STRICT_PLANES[plane]})
    if not enabled:
        values = merge_values(
            values, {"global": {"secretsFromFiles": {"enabled": False}, "dbBootstrapper": db_bootstrapper_toggle(False)}}
        )
    return merge_values(values, override or {})


_STRICT_RENDERS = {}


def strict_render(plane, enabled=True):
    """The all-on (or all-off) render of a plane, rendered once per worker."""
    key = (plane, enabled)
    if key not in _STRICT_RENDERS:
        _STRICT_RENDERS[key] = render_chart(
            kube_version=newest_supported_kube_version, values=strict_values(plane, enabled=enabled)
        )
    return _STRICT_RENDERS[key]


def secret_key_refs(docs):
    """Every (workload, container, env) the render takes from a secretKeyRef."""
    return {
        (name, container["name"], env["name"])
        for name, spec in pod_specs(docs)
        for container in all_containers(spec)
        for env in container.get("env") or []
        if "secretKeyRef" in (env.get("valueFrom") or {})
    }


def visible_loader_files(spec, container):
    """The file paths a container can read from loader secret volumes: every item of a
    whole-volume mount, or just the one a subPath mount names."""
    volumes = {v["name"]: v for v in spec.get("volumes") or []}
    paths = set()
    for mount in container.get("volumeMounts") or []:
        if mount["name"] not in STRICT_LOADER_VOLUMES or mount["name"] not in volumes:
            continue
        filenames = _secret_volume_filenames(volumes[mount["name"]]) or set()
        if mount.get("subPath"):
            if mount["subPath"] in filenames:
                paths.add(mount["mountPath"])
        else:
            paths |= {f"{mount['mountPath'].rstrip('/')}/{filename}" for filename in filenames}
    return paths


def managed_names(container):
    """The names the container's loaders refuse in its environment, for a gated container."""
    env_vars = get_env_vars_dict(container.get("env") or [])
    names = set()
    for gate in loader_gates_on(container):
        if gate == "HOUSTON_SECRETS_FROM_FILES":
            extra = env_vars.get("HOUSTON_SECRETS_FROM_FILES_EXTRA", "")
            names |= HOUSTON_MANAGED_SECRET_ENV_VARS | {n for n in extra.split(",") if n}
        elif gate == "COMMANDER_SECRETS_FROM_FILES":
            names |= COMMANDER_SECRET_ENV_VARS
        elif gate == "KUIPER_SECRETS_FROM_FILES":
            names |= KUIPER_MANAGED_SECRET_ENV_VARS
        elif gate == "DB_BOOTSTRAPPER_SECRETS_FROM_FILES":
            names |= DB_BOOTSTRAPPER_MANAGED_SECRET_ENV_VARS
    return names


@pytest.mark.parametrize("plane", list(STRICT_PLANES))
def test_every_gated_container_is_strictly_consistent(plane):
    """The invariant strict mode rests on, swept over every container whose loader is on.

    - no managed name in its environment (with a value, or any valueFrom);
    - no secretKeyRef at all;
    - every <VAR>_FILE it advertises is a file a loader volume projects;
    - the files it can see in loader volumes are exactly the ones it advertises;
    - houston's EXTRA lists exactly the <VAR>_FILEs beyond the loader's built-in list.
    """
    docs = strict_render(plane)
    problems = []
    gated = 0
    for name, spec in pod_specs(docs):
        for container in all_containers(spec):
            if not loader_gates_on(container):
                continue
            gated += 1
            where = f"{name}/{container['name']}"
            env = container.get("env") or []
            env_vars = get_env_vars_dict(env)
            managed = managed_names(container)
            kuiper = "KUIPER_SECRETS_FROM_FILES" in loader_gates_on(container)
            for entry in env:
                entry_name = entry["name"].upper() if kuiper else entry["name"]
                if entry_name in managed and (entry.get("value") or entry.get("valueFrom")):
                    problems.append(f"{where}: managed secret {entry['name']} is in its environment")
                if "secretKeyRef" in (entry.get("valueFrom") or {}):
                    problems.append(f"{where}: {entry['name']} comes from a secretKeyRef")

            advertised = {v for k, v in env_vars.items() if k.endswith("_FILE") and isinstance(v, str)}
            visible = visible_loader_files(spec, container)
            if advertised - visible:
                problems.append(f"{where}: advertises {sorted(advertised - visible)} with no file behind them")
            if visible - advertised:
                problems.append(f"{where}: can load {sorted(visible - advertised)} without advertising them")

            if "HOUSTON_SECRETS_FROM_FILES" in loader_gates_on(container):
                # The loader only reads a file beyond its built-in list if EXTRA names
                # it, and requires every name EXTRA lists. An operator secret may reuse
                # a built-in name (EMAIL__SMTP_URL is the documented example).
                extra = {n for n in env_vars.get("HOUSTON_SECRETS_FROM_FILES_EXTRA", "").split(",") if n}
                files = {k.removesuffix("_FILE") for k in env_vars if k.endswith("_FILE")}
                if extra - files:
                    problems.append(f"{where}: EXTRA lists {sorted(extra - files)} with no <VAR>_FILE")
                if files - HOUSTON_MANAGED_SECRET_ENV_VARS - extra:
                    problems.append(
                        f"{where}: advertises {sorted(files - HOUSTON_MANAGED_SECRET_ENV_VARS - extra)} the loader never reads"
                    )
    assert problems == [], "\n".join(problems)
    # A floor, so the sweep cannot pass by matching nothing.
    assert gated >= {"unified": 25, "control-ha": 20, "data": 6}[plane], f"only {gated} gated containers rendered"


# What stays a secretKeyRef with every converted component on: the components with no
# secrets-from-files switch yet (§7 of the strict-mode plan). Pinned so a new
# secretKeyRef in a component that is on fails here instead of shipping.
RESIDUAL_SECRET_KEY_REFS = {
    "unified": {
        ("release-name-grafana", "wait-for-db", "GF_DATABASE_URL"),
        ("release-name-grafana", "grafana", "GF_DATABASE_URL"),
        ("release-name-registry", "registry", "REGISTRY_NOTIFICATIONS_ENDPOINTS_0_HEADERS"),
        ("release-name-api-server", "apiserver", "LAMINAR_DATABASE_URL"),
        ("release-name-hypervisor", "hypervisor", "LAMINAR_DATABASE_URL"),
        ("release-name-hypervisor", "hypervisor", "LAMINAR_JWKS"),
        ("release-name-mcp-server", "mcp-server", "MCP_TOKEN"),
    },
    "control-ha": {
        ("release-name-grafana", "wait-for-db", "GF_DATABASE_URL"),
        ("release-name-grafana", "grafana", "GF_DATABASE_URL"),
        ("release-name-mcp-server", "mcp-server", "MCP_TOKEN"),
    },
    "data": {
        ("release-name-registry", "registry", "REGISTRY_NOTIFICATIONS_ENDPOINTS_0_HEADERS"),
        ("release-name-api-server", "apiserver", "LAMINAR_DATABASE_URL"),
        ("release-name-hypervisor", "hypervisor", "LAMINAR_DATABASE_URL"),
        ("release-name-hypervisor", "hypervisor", "LAMINAR_JWKS"),
    },
}


@pytest.mark.parametrize("plane", list(STRICT_PLANES))
def test_residual_secret_key_refs_are_pinned(plane):
    assert secret_key_refs(strict_render(plane)) == RESIDUAL_SECRET_KEY_REFS[plane]


# ── Strict: the per-switch matrix ──────────────────────────────────────────────
#
# Turning one component off is the way out of strict mode, so each switch must
# take exactly its own component back to environment variables -- the original
# secretKeyRefs, and no gate, <VAR>_FILE, secret volume, wait-for-secret or fsGroup
# of its own -- and leave everything else on. Each case renders the all-on chart
# with one switch off and compares it with the all-on render.

HOUSTON_DB_REFS = {"DATABASE__CONNECTION", "DATABASE_URL", "DEPLOYMENTS__DATABASE__CONNECTION", "EMAIL__SMTP_URL"}
HOUSTON_LOADER_CONTAINERS = {
    ("release-name-houston", "houston"),
    ("release-name-houston-worker", "houston-worker"),
    ("release-name-houston-db-migrations", "houston-db-migrations-job"),
    ("release-name-houston-upgrade-deployments", "post-upgrade-job"),
    ("release-name-houston-update-runtime-check", "update-check"),
    ("release-name-houston-update-check", "update-check"),
    ("release-name-houston-cleanup-cluster-audits", "cleanup"),
    ("release-name-houston-cleanup-deploy-revisions", "cleanup"),
    ("release-name-houston-cleanup-deployments", "cleanup"),
    ("release-name-houston-cleanup-task-usage-data", "cleanup"),
    ("release-name-houston-populate-daily-task-metrics", "populate-daily-task-metrics"),
    ("release-name-houston-populate-hourly-ta-metrics", "populate-daily-task-metrics"),
    ("release-name-houston-sync-dataplane-clusters", "sync-dataplane-clusters"),
}
HOUSTON_GATED_WORKLOADS = {
    "release-name-houston",
    "release-name-houston-worker",
    "release-name-houston-db-migrations",
    "release-name-houston-upgrade-deployments",
}
BOOTSTRAPPERS = DB_BOOTSTRAPPER_CONTAINERS
# Every houston-family workload with a wait-for-secret gate while houston is on.
HOUSTON_WAITING_WORKLOADS = HOUSTON_GATED_WORKLOADS | HOUSTON_CRONJOBS

# Under controlPlaneHA the houston family also runs the cp-refresh hook, and CP_ID is
# one of its secrets: a file while houston is on, a secretKeyRef again once it is off.
CP_REFRESH_WORKLOAD = "release-name-houston-cp-refresh"
HA_HOUSTON_LOADER_CONTAINERS = HOUSTON_LOADER_CONTAINERS | {(CP_REFRESH_WORKLOAD, "refresh-cp-chart-version-job")}
HA_WAIT_FOR_DB_CONTAINERS = WAIT_FOR_DB_CONTAINERS | {(CP_REFRESH_WORKLOAD, "wait-for-db")}
HA_HOUSTON_GATED_WORKLOADS = HOUSTON_GATED_WORKLOADS | {CP_REFRESH_WORKLOAD}


def refs(containers, names):
    return {(workload, container, name) for workload, container in containers for name in names}


SWITCH_MATRIX = {
    "navigator": {
        "values": {"astronomer": {"navigator": _switch(False)}},
        "refs": refs({("release-name-navigator", "navigator")}, {"DATABASE_URL", "DEPLOYMENTS__DATABASE__CONNECTION", "NAV_TOKEN"}),
        "stopped": {("release-name-navigator", "navigator"), ("release-name-navigator", "wait-for-secret")},
        "volumes": {"release-name-navigator": {"navigator-secrets"}},
    },
    "dp-link": {
        "values": {"astronomer": {"dpLink": _switch(False)}},
        "refs": refs(
            {("release-name-dp-link", "dp-link")},
            {"DATABASE__CONNECTION", "DATABASE_URL", "DEPLOYMENTS__DATABASE__CONNECTION", "DPL_TOKEN"},
        ),
        "stopped": {("release-name-dp-link", "dp-link"), ("release-name-dp-link", "wait-for-secret")},
        "volumes": {"release-name-dp-link": {"dp-link-secrets"}},
    },
    "houston": {
        "values": {"astronomer": {"houston": _switch(False)}},
        "refs": refs(HOUSTON_LOADER_CONTAINERS | WAIT_FOR_DB_CONTAINERS, HOUSTON_DB_REFS)
        | {("release-name-houston", "houston", "REGISTRY__AUTH_HEADER")},
        "stopped": HOUSTON_LOADER_CONTAINERS | {(w, "wait-for-secret") for w in HOUSTON_WAITING_WORKLOADS},
        "volumes": {w: {"houston-secrets"} for w, _c in HOUSTON_LOADER_CONTAINERS}
        | {"release-name-houston": {"houston-secrets", "houston-registry-auth-secret"}},
        # Their ap-db-bootstrapper is still on, and needs the fsGroup for its own file.
        "keep_fs_group": HOUSTON_GATED_WORKLOADS,
    },
    "vector-sidecar": {
        "values": {"astronomer": {"houston": {"logging": {"loggingSidecar": _switch(False)}}}},
        "refs": refs(
            {("release-name-houston", "vector"), ("release-name-houston-worker", "vector")}, {"ES_USERNAME", "ES_PASSWORD"}
        ),
        "stopped": {("release-name-houston", "vector"), ("release-name-houston-worker", "vector")},
        "volumes": {
            "release-name-houston": {"vector-elasticsearch-secret"},
            "release-name-houston-worker": {"vector-elasticsearch-secret"},
        },
        "keep_fs_group": {"release-name-houston", "release-name-houston-worker"},
    },
    "commander": {
        "values": {"astronomer": {"commander": _switch(False)}},
        "refs": refs({("release-name-commander", "commander")}, COMMANDER_SECRET_ENV_VARS)
        | {("release-name-commander", "flightdeck-db-migrations", "COMMANDER_FLIGHTDECK_DSN")},
        "stopped": {
            ("release-name-commander", "commander"),
            ("release-name-commander", "flightdeck-db-migrations"),
            ("release-name-commander", "wait-for-secret"),
        },
        "volumes": {"release-name-commander": {"commander-secrets"}},
        "keep_fs_group": {"release-name-commander"},
    },
    "pilot": {
        "values": {"astronomer": {"pilot": _switch(False)}},
        "refs": {("release-name-pilot", "pilot", "COMMANDER_FLIGHTDECK_DSN")},
        "stopped": {("release-name-pilot", "pilot"), ("release-name-pilot", "wait-for-secret")},
        "volumes": {"release-name-pilot": {"flightdeck-dsn-secret"}},
    },
    "db-bootstrapper": {
        "values": {"global": {"dbBootstrapper": db_bootstrapper_toggle(False)}},
        "refs": refs(BOOTSTRAPPERS, {"BOOTSTRAP_DB"}),
        "stopped": BOOTSTRAPPERS,
        "volumes": {workload: {DB_BOOTSTRAPPER_VOLUME} for workload, _c in BOOTSTRAPPERS},
        # houston and commander are still on in those pods; grafana and laminar have nothing else.
        "keep_fs_group": HOUSTON_GATED_WORKLOADS | {"release-name-commander"},
    },
    "filesd-reloader": {
        "values": {"prometheus": {"filesdReloader": _switch(False)}},
        "refs": {("release-name-prometheus", "filesd-reloader", "DATABASE_URL")},
        "stopped": {("release-name-prometheus", "filesd-reloader")},
        "volumes": {"release-name-prometheus": {"filesd-reloader-secrets"}},
    },
    "postgresql": {
        "values": {"postgresql": _switch(False)},
        "refs": {
            ("release-name-postgresql-master", "release-name-postgresql", "POSTGRES_PASSWORD"),
            ("release-name-postgresql-master", "release-name-postgresql", "POSTGRES_REPLICATION_PASSWORD"),
            ("release-name-postgresql-master", "metrics", "DATA_SOURCE_PASS"),
            ("release-name-postgresql-slave", "release-name-postgresql", "POSTGRES_PASSWORD"),
            ("release-name-postgresql-slave", "release-name-postgresql", "POSTGRES_REPLICATION_PASSWORD"),
        },
        "stopped": {
            ("release-name-postgresql-master", "release-name-postgresql"),
            ("release-name-postgresql-master", "metrics"),
            ("release-name-postgresql-slave", "release-name-postgresql"),
        },
        "volumes": {
            "release-name-postgresql-master": {"postgresql-password"},
            "release-name-postgresql-slave": {"postgresql-password"},
        },
    },
    "postgres-exporter": {
        "values": {"prometheus-postgres-exporter": _switch(False)},
        "refs": {("release-name-prometheus-postgres-exporter", "prometheus-postgres-exporter", "DATA_SOURCE_PASS")},
        "stopped": {("release-name-prometheus-postgres-exporter", "prometheus-postgres-exporter")},
        "volumes": {"release-name-prometheus-postgres-exporter": {PG_EXPORTER_SECRET_VOLUME}},
    },
    "external-es-proxy": {
        "values": {"global": {"customLogging": _switch(False)}},
        "refs": {
            ("release-name-external-es-proxy", "external-es-proxy", "ES_SECRET_NAME"),
            ("release-name-external-es-proxy", "awsproxy", "AWS_ACCESS_KEY_ID"),
            ("release-name-external-es-proxy", "awsproxy", "AWS_SECRET_ACCESS_KEY"),
        },
        "stopped": {("release-name-external-es-proxy", "external-es-proxy"), ("release-name-external-es-proxy", "awsproxy")},
        # awssecret predates this feature and is rendered either way; only es-secret is ours.
        "volumes": {"release-name-external-es-proxy": {"es-secret"}},
    },
    "houston-under-ha": {
        "plane": "control-ha",
        "values": {"astronomer": {"houston": _switch(False)}},
        "refs": refs(HA_HOUSTON_LOADER_CONTAINERS | HA_WAIT_FOR_DB_CONTAINERS, HOUSTON_DB_REFS | {"CP_ID"})
        | {("release-name-houston", "houston", "REGISTRY__AUTH_HEADER")},
        "stopped": HA_HOUSTON_LOADER_CONTAINERS | {(w, "wait-for-secret") for w in HA_HOUSTON_GATED_WORKLOADS | HOUSTON_CRONJOBS},
        "volumes": {w: {"houston-secrets"} for w, _c in HA_HOUSTON_LOADER_CONTAINERS}
        | {"release-name-houston": {"houston-secrets", "houston-registry-auth-secret"}},
        "keep_fs_group": HA_HOUSTON_GATED_WORKLOADS,
    },
    "navigator-under-ha": {
        "plane": "control-ha",
        "values": {"astronomer": {"navigator": _switch(False)}},
        "refs": refs(
            {("release-name-navigator", "navigator")}, {"DATABASE_URL", "DEPLOYMENTS__DATABASE__CONNECTION", "NAV_TOKEN", "CP_ID"}
        ),
        "stopped": {("release-name-navigator", "navigator"), ("release-name-navigator", "wait-for-secret")},
        "volumes": {"release-name-navigator": {"navigator-secrets"}},
    },
    "dp-link-under-ha": {
        "plane": "control-ha",
        "values": {"astronomer": {"dpLink": _switch(False)}},
        "refs": refs(
            {("release-name-dp-link", "dp-link")},
            {"DATABASE__CONNECTION", "DATABASE_URL", "DEPLOYMENTS__DATABASE__CONNECTION", "DPL_TOKEN", "CP_ID"},
        ),
        "stopped": {("release-name-dp-link", "dp-link"), ("release-name-dp-link", "wait-for-secret")},
        "volumes": {"release-name-dp-link": {"dp-link-secrets"}},
    },
    "federation-auth": {
        "plane": "data",
        "values": {"prometheus": {"federation": {"auth": _switch(False)}}},
        "refs": {("release-name-prometheus-federation-auth", "federation-auth", "REGISTRY_AUTH_TOKEN")},
        "stopped": {("release-name-prometheus-federation-auth", "federation-auth")},
        "volumes": {"release-name-prometheus-federation-auth": {FEDERATION_AUTH_SECRET_VOLUME}},
    },
}


def file_mode_containers(docs):
    """(workload, container) for every container that reads secrets from files: its
    loader gate is on, or it mounts a secret where file mode puts them."""
    roots = ("/etc/astronomer/secrets", "/etc/houston/secrets", "/etc/vector/secrets")
    return {
        (name, container["name"])
        for name, spec in pod_specs(docs)
        for container in all_containers(spec)
        if loader_gates_on(container) or any(m["mountPath"].startswith(roots) for m in container.get("volumeMounts") or [])
    }


@pytest.mark.parametrize("switch", list(SWITCH_MATRIX))
def test_one_switch_off_takes_only_its_component_back_to_env_vars(switch):
    """One render per case, compared with the all-on and all-off renders of the same
    plane, which are rendered once and shared across the cases."""
    case = SWITCH_MATRIX[switch]
    plane = case.get("plane", "unified")
    all_on = strict_render(plane)
    all_off = dict(pod_specs(strict_render(plane, enabled=False)))
    docs = render_chart(kube_version=newest_supported_kube_version, values=strict_values(plane, case["values"]))
    specs = dict(pod_specs(docs))

    # Its own secrets are secretKeyRefs again, and nothing else changed.
    assert secret_key_refs(docs) - secret_key_refs(all_on) == case["refs"]
    assert secret_key_refs(all_on) - secret_key_refs(docs) == set()

    # Exactly its containers stopped reading files -- wait-for-secret included -- and
    # every other component is still on.
    assert file_mode_containers(all_on) - file_mode_containers(docs) == case["stopped"]
    assert file_mode_containers(docs) - file_mode_containers(all_on) == set()

    for workload, container_name in case["stopped"]:
        container = next((c for c in all_containers(specs[workload]) if c["name"] == container_name), None)
        if container is None:
            assert container_name == "wait-for-secret", f"{workload}/{container_name} disappeared"
            continue
        env_vars = get_env_vars_dict(container.get("env") or [])
        assert not loader_gates_on(container), f"{workload}/{container_name} still sets its gate"
        assert not [k for k in env_vars if k.endswith("_FILE")], f"{workload}/{container_name} still advertises a file"

    for workload, volumes in case["volumes"].items():
        names = {v["name"] for v in specs[workload].get("volumes") or []}
        assert not volumes & names, f"{workload} still has {sorted(volumes & names)}"

    for workload in {w for w, _c in case["stopped"]} | set(case["volumes"]):
        fs_group = (specs[workload].get("securityContext") or {}).get("fsGroup")
        if workload in case.get("keep_fs_group", set()):
            assert fs_group is not None, f"{workload} lost the fsGroup another component in the pod still needs"
        else:
            # Back to exactly what the pod had with the feature off everywhere.
            assert specs[workload].get("securityContext") == all_off[workload].get("securityContext"), workload
