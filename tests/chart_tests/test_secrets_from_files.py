"""Tests for loading secrets from mounted files instead of environment variables.

The feature is cross-cutting: one toggle changes ~16 workloads, so most of these
tests sweep the whole rendered chart rather than a single template.
"""

import re

import pytest
import yaml

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


# Vector Sidecar
#
# Unlike the houston loader, this uses Vector's own native `secret` directory
# backend, so it has its own toggle. Verified end to end against the pinned
# ap-vector:0.53.0 image: the ES sink's Basic auth header decoded byte-for-byte
# to the mounted file contents.

VECTOR_SECRET_ENVS = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "ES_USERNAME", "ES_PASSWORD"}

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


def vector_values(enabled=None, **sidecar):
    """Both credential-using sinks on, with an optional secretsFromFiles setting."""
    sidecar_values = {
        "enabled": True,
        "cloudwatch": {"enabled": True, "useIRSA": False, "region": "us-east-1"},
        "elasticsearch": {"enabled": True, "endpoint": "https://es.example.com:9200"},
        **sidecar,
    }
    if enabled is not None:
        sidecar_values["secretsFromFiles"] = {"enabled": enabled}
    return {
        "global": {"plane": {"mode": "unified"}},
        "astronomer": {"houston": {"logging": {"loggingSidecar": sidecar_values}}},
    }


def vector_config(docs):
    """The parsed vector.yaml out of whichever configmap is in docs."""
    configmap = next(d for d in docs if d["kind"] == "ConfigMap")
    return yaml.safe_load(configmap["data"]["vector.yaml"])


@pytest.mark.parametrize("label,deployment,configmap", VECTOR_TEMPLATES, ids=[t[0] for t in VECTOR_TEMPLATES])
class TestVectorSidecarSecretsFromFiles:
    def test_defaults_keep_env_vars(self, label, deployment, configmap):
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=vector_values(),
            show_only=[deployment, configmap],
        )
        vector = get_containers_by_name(next(d for d in docs if d["kind"] == "Deployment"))["vector"]
        env_vars = get_env_vars_dict(vector["env"])
        assert VECTOR_SECRET_ENVS <= set(env_vars)

        config = vector_config(docs)
        assert "secret" not in config
        assert config["sinks"]["cloudwatch"]["auth"]["access_key_id"] == "${AWS_ACCESS_KEY_ID}"
        assert config["sinks"]["elasticsearch"]["auth"]["password"] == "${ES_PASSWORD}"

    def test_enabled_replaces_env_with_secret_placeholders(self, label, deployment, configmap):
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=vector_values(enabled=True),
            show_only=[deployment, configmap],
        )
        doc = next(d for d in docs if d["kind"] == "Deployment")
        spec = doc["spec"]["template"]["spec"]
        vector = get_containers_by_name(doc)["vector"]

        # No credential ever reaches the pod spec.
        assert not VECTOR_SECRET_ENVS & set(get_env_vars_dict(vector["env"]))

        volumes = {v["name"]: v for v in spec["volumes"]}
        assert volumes["vector-cloudwatch-secret"]["secret"]["items"] == [
            {"key": "aws_access_key_id", "path": "aws_access_key_id"},
            {"key": "aws_secret_access_key", "path": "aws_secret_access_key"},
        ]
        assert volumes["vector-elasticsearch-secret"]["secret"]["items"] == [
            {"key": "username", "path": "username"},
            {"key": "password", "path": "password"},
        ]

        mounts = {m["name"]: m for m in vector["volumeMounts"]}
        assert mounts["vector-cloudwatch-secret"]["mountPath"] == "/etc/vector/secrets/cloudwatch"
        assert mounts["vector-elasticsearch-secret"]["mountPath"] == "/etc/vector/secrets/elasticsearch"
        assert all(mounts[n]["readOnly"] for n in ("vector-cloudwatch-secret", "vector-elasticsearch-secret"))

        config = vector_config(docs)
        assert config["sinks"]["cloudwatch"]["auth"] == {
            "access_key_id": "SECRET[cloudwatch.aws_access_key_id]",
            "secret_access_key": "SECRET[cloudwatch.aws_secret_access_key]",
        }
        assert config["sinks"]["elasticsearch"]["auth"] == {
            "strategy": "basic",
            "user": "SECRET[elasticsearch.username]",
            "password": "SECRET[elasticsearch.password]",
        }

        # Each backend's directory must match the mountPath it reads from.
        assert config["secret"]["cloudwatch"]["path"] == mounts["vector-cloudwatch-secret"]["mountPath"]
        assert config["secret"]["elasticsearch"]["path"] == mounts["vector-elasticsearch-secret"]["mountPath"]

    def test_backend_names_are_word_characters_only(self, label, deployment, configmap):
        """Vector's placeholder regex is SECRET\\[([[:word:]]+)\\....\\].

        A hyphen in a backend name does not match, so the placeholder is left in
        the config verbatim and Vector ships the literal string as a credential --
        a silent failure. Confirmed against ap-vector:0.53.0.
        """
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=vector_values(enabled=True),
            show_only=[deployment, configmap],
        )
        for backend in vector_config(docs)["secret"]:
            assert re.fullmatch(r"\w+", backend), f"backend {backend!r} will not be substituted"

    def test_every_backend_removes_trailing_whitespace(self, label, deployment, configmap):
        """Without this, the newline a Secret mount adds becomes a trailing space.

        The value sits in a double-quoted YAML scalar, so the newline is folded to
        a space rather than dropped, and the credential is silently wrong.
        """
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=vector_values(enabled=True),
            show_only=[deployment, configmap],
        )
        for name, backend in vector_config(docs)["secret"].items():
            assert backend["type"] == "directory"
            assert backend["remove_trailing_whitespace"] is True, f"{name} would keep the trailing newline"

    def test_config_change_rolls_the_pod(self, label, deployment, configmap):
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=vector_values(enabled=True),
            show_only=[deployment],
        )
        annotations = docs[0]["spec"]["template"]["metadata"]["annotations"]
        assert "checksum/vector-config" in annotations

    @pytest.mark.parametrize(
        "sidecar_override,expected_backends",
        [
            ({"cloudwatch": {"enabled": True, "useIRSA": True, "region": "us-east-1"}}, ["elasticsearch"]),
            ({"elasticsearch": {"enabled": True, "endpoint": "https://es:9200", "auth": {"strategy": "none"}}}, ["cloudwatch"]),
            (
                {
                    "cloudwatch": {"enabled": False},
                    "elasticsearch": {"enabled": False},
                    "gcpCloudLogging": {"enabled": True, "projectId": "p"},
                },
                None,
            ),
        ],
        ids=["cloudwatch_uses_irsa", "es_auth_not_basic", "only_gcp"],
    )
    def test_only_mounts_credentials_a_sink_actually_needs(self, label, deployment, configmap, sidecar_override, expected_backends):
        docs = render_chart(
            kube_version=newest_supported_kube_version,
            values=vector_values(enabled=True, **sidecar_override),
            show_only=[deployment, configmap],
        )
        config = vector_config(docs)
        spec = next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"]
        volumes = {v["name"] for v in spec["volumes"]}

        if expected_backends is None:
            assert "secret" not in config
            assert not {"vector-cloudwatch-secret", "vector-elasticsearch-secret"} & volumes
        else:
            assert sorted(config["secret"]) == sorted(expected_backends)
            for backend in ("cloudwatch", "elasticsearch"):
                volume = f"vector-{backend}-secret"
                assert (volume in volumes) is (backend in expected_backends)


def test_vector_toggle_is_independent_of_houston_toggle():
    """The sidecar uses Vector's native mechanism, not the houston loader."""
    values = vector_values(enabled=False)
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
    assert VECTOR_SECRET_ENVS <= set(get_env_vars_dict(containers["vector"]["env"]))
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

PG_PASSWORD_FILE = "/run/secrets/postgresql-password"


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
        assert esproxy_mount["mountPath"] == "/run/secrets"
        assert esproxy_mount["readOnly"] is True

        assert "init_by_lua_block" in configs["nginx.conf"]
        assert "/run/secrets/ES_SECRET" in configs["nginx.conf"]
        # The `elastic` key holds raw credentials, so the lua must encode them --
        # matching the ES_SECRET_NAME branch, not the pre-encoded ES_SECRET one.
        assert "ngx.encode_base64(ES_SECRET_FROM_FILE)" in configs["setenv.lua"]

        # awsproxy: no env, preamble reads the files before exec.
        awsproxy = containers["awsproxy"]
        aws_env = get_env_vars_dict(awsproxy.get("env") or [])
        assert "AWS_ACCESS_KEY_ID" not in aws_env
        assert "AWS_SECRET_ACCESS_KEY" not in aws_env
        args = awsproxy["args"][0]
        assert 'export AWS_ACCESS_KEY_ID="$(cat /run/secrets/aws_access_key)"' in args
        assert 'export AWS_SECRET_ACCESS_KEY="$(cat /run/secrets/aws_secret_key)"' in args
        assert args.strip().endswith("exec aws-es-proxy -listen :9203")
        aws_mount = next(m for m in awsproxy["volumeMounts"] if m["name"] == "awssecret")
        assert aws_mount["mountPath"] == "/run/secrets"

    def test_setenv_lua_does_no_file_io_itself(self):
        """setenv.lua runs per request; reading the file there would hit the disk
        on every proxied request. The read belongs in init_by_lua_block."""
        _deployment, configs = esp_parts(esp_docs(enabled=True))
        assert "io.open" in configs["nginx.conf"]
        assert "io.open" not in configs["setenv.lua"]

    def test_inline_secret_value_takes_precedence_over_the_file(self):
        """global.customLogging.secret is a literal value, not a Secret reference,
        so there is nothing to move to a file and the lua's ES_SECRET branch wins.

        The literal below is a test fixture standing in for an operator-supplied
        value, hence the S106 suppression.
        """
        deployment, _configs = esp_parts(esp_docs(enabled=True, secret="cHJlLWVuY29kZWQ="))  # noqa: S106
        spec = deployment["spec"]["template"]["spec"]
        esproxy = next(c for c in spec["containers"] if c["name"] == "external-es-proxy")

        assert get_env_vars_dict(esproxy["env"])["ES_SECRET"] == "cHJlLWVuY29kZWQ="
        assert "es-secret" not in {v["name"] for v in spec["volumes"]}
        assert "es-secret" not in {m["name"] for m in esproxy["volumeMounts"]}

    def test_no_preamble_when_aws_credentials_are_not_used(self):
        """With an IAM role instead of keys, awsproxy still renders but has no
        credentials to read, so the args must stay untouched."""
        docs = esp_docs(enabled=True, awsSecretName=None, awsIAMRole="arn:aws:iam::123:role/es")
        deployment, _configs = esp_parts(docs)
        awsproxy = next(c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == "awsproxy")
        assert awsproxy["args"] == ["aws-es-proxy -listen :9203"]
        assert "cat /run/secrets" not in awsproxy["args"][0]

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
