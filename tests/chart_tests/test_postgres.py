import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPostgresql:
    @staticmethod
    def postgresql_common_tests(doc):
        """Test common for postgresql statefulset."""
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-postgresql"

    def test_postgresql_statefulset_defaults(self, kube_version):
        """Test postgresql statefulset is good with defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"postgresql": {"enabled": True}}},
            show_only=["charts/postgresql/templates/statefulset.yaml"],
        )

        assert len(docs) == 1
        sts = docs[0]
        self.postgresql_common_tests(sts)
        assert len(sts["spec"]["template"]["spec"]["containers"]) == 1
        containers = get_containers_by_name(doc=sts, include_init_containers=True)
        assert containers["release-name-postgresql"]["volumeMounts"] == [
            {"mountPath": "/tmp", "name": "tmp"},
            {"mountPath": "/var/run/postgresql", "name": "postgresql-run"},
            {"name": "data", "mountPath": "/bitnami/postgresql", "subPath": None},
        ]
        assert "persistentVolumeClaimRetentionPolicy" not in sts["spec"]

        # The postgresql-run emptyDir is created root-owned by kubelet; fsGroup only
        # changes its GID, not its UID, so the non-root postgres container can't chmod
        # it itself. This init container hands ownership to the runAsUser before the
        # main container starts..
        init_containers = sts["spec"]["template"]["spec"]["initContainers"]
        assert len(init_containers) == 1
        init_container = init_containers[0]
        assert init_container["name"] == "init-postgresql-run"
        assert init_container["securityContext"]["runAsUser"] == 0
        assert init_container["securityContext"]["runAsNonRoot"] is False
        assert init_container["volumeMounts"] == [{"name": "postgresql-run", "mountPath": "/var/run/postgresql"}]
        assert "chown 1001:1001 /var/run/postgresql" in "\n".join(init_container["command"])

    def test_postgresql_statefulset_slaves_volume_mounts(self, kube_version):
        """Test postgresql slave statefulset mounts a writable /var/run/postgresql.

        readOnlyRootFilesystem is set on the slave container, so unix_socket_directories
        must resolve to a writable, mounted path. See PINF-347.
        """
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"postgresql": {"enabled": True}},
                "postgresql": {"replication": {"enabled": True}},
            },
            show_only=["charts/postgresql/templates/statefulset-slaves.yaml"],
        )

        assert len(docs) == 1
        sts = docs[0]
        containers = get_containers_by_name(doc=sts, include_init_containers=True)
        volume_mounts = containers["release-name-postgresql"]["volumeMounts"]
        assert {"name": "postgresql-run", "mountPath": "/var/run/postgresql"} in volume_mounts

        volumes = sts["spec"]["template"]["spec"]["volumes"]
        assert {"name": "postgresql-run", "emptyDir": {}} in volumes

        init_containers = sts["spec"]["template"]["spec"]["initContainers"]
        assert any(c["name"] == "init-postgresql-run" for c in init_containers)

    def test_postgresql_statefulset_with_private_registry_enabled(self, kube_version):
        """Test postgresql with privateRegistry=True."""
        repository = "private-repository.example.com"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        "repository": repository,
                    },
                    "postgresql": {"enabled": True},
                },
            },
            show_only=[
                "charts/postgresql/templates/statefulset.yaml",
            ],
        )

        for doc in docs:
            c_by_name = get_containers_by_name(doc=doc, include_init_containers=True)
            for name, container in c_by_name.items():
                assert container["image"].startswith(repository), (
                    f"Container named '{name}' does not use registry '{repository}': {container}"
                )

    def test_postgresql_persistentVolumeClaimRetentionPolicy(self, kube_version):
        test_persistentVolumeClaimRetentionPolicy = {
            "whenDeleted": "Delete",
            "whenScaled": "Retain",
        }
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {"postgresql": {"enabled": True}},
                "postgresql": {
                    "persistence": {
                        "persistentVolumeClaimRetentionPolicy": test_persistentVolumeClaimRetentionPolicy,
                    },
                },
            },
            show_only=[
                "charts/postgresql/templates/statefulset.yaml",
            ],
        )

        assert len(doc) == 1

        assert "persistentVolumeClaimRetentionPolicy" in doc[0]["spec"]
        assert test_persistentVolumeClaimRetentionPolicy == doc[0]["spec"]["persistentVolumeClaimRetentionPolicy"]

    def test_postgresql_replication_persistentVolumeClaimRetentionPolicy(self, kube_version):
        test_persistentVolumeClaimRetentionPolicy = {
            "whenDeleted": "Delete",
            "whenScaled": "Retain",
        }
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {"postgresql": {"enabled": True}},
                "postgresql": {
                    "replication": {
                        "enabled": True,
                    },
                    "persistence": {
                        "persistentVolumeClaimRetentionPolicy": test_persistentVolumeClaimRetentionPolicy,
                    },
                },
            },
            show_only=[
                "charts/postgresql/templates/statefulset-slaves.yaml",
            ],
        )

        assert len(doc) == 1

        assert "persistentVolumeClaimRetentionPolicy" in doc[0]["spec"]
        assert test_persistentVolumeClaimRetentionPolicy == doc[0]["spec"]["persistentVolumeClaimRetentionPolicy"]

    def test_postgresql_with_global_nodepool_config(self, kube_version, global_platform_node_pool_config):
        """Test Postgresql with nodeSelector, affinity, tolerations and global config."""
        values = {"global": {"platformNodePool": global_platform_node_pool_config, "postgresql": {"enabled": True}}}
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/postgresql/templates/statefulset.yaml"],
        )

        assert len(docs) == 1
        self.postgresql_common_tests(docs[0])
        spec = docs[0]["spec"]["template"]["spec"]
        assert spec["nodeSelector"]["role"] == "astro"
        assert len(spec["affinity"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["global"]["platformNodePool"]["tolerations"]

    def test_postgresql_platform_nodepool_subchart_overrides(self, kube_version, global_platform_node_pool_config):
        """Test Postgresql with nodeSelector, affinity, tolerations and subchart config overrides."""
        global_platform_node_pool_config["nodeSelector"] = {"role": "astropostgresql"}
        values = {
            "global": {"postgresql": {"enabled": True}},
            "postgresql": {
                "master": {
                    "nodeSelector": global_platform_node_pool_config["nodeSelector"],
                    "affinity": global_platform_node_pool_config["affinity"],
                    "tolerations": global_platform_node_pool_config["tolerations"],
                },
            },
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/postgresql/templates/statefulset.yaml"],
        )

        assert len(docs) == 1
        self.postgresql_common_tests(docs[0])
        spec = docs[0]["spec"]["template"]["spec"]
        assert spec["nodeSelector"]["role"] == "astropostgresql"
        assert len(spec["affinity"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["postgresql"]["master"]["tolerations"]

    def test_postgresql_platform_nodepool_subchart_overrides_with_ha(self, kube_version, global_platform_node_pool_config):
        """Test Postgresql with nodeSelector, affinity, tolerations and subchart config overrides with ha."""
        values = {
            "global": {"postgresql": {"enabled": True}},
            "postgresql": {
                "replication": {
                    "enabled": True,
                },
                "master": {
                    "nodeSelector": {"role": "astromasterpostgresql"},
                    "affinity": global_platform_node_pool_config["affinity"],
                    "tolerations": global_platform_node_pool_config["tolerations"],
                },
                "slave": {
                    "nodeSelector": {"role": "astroslavepostgresql"},
                    "affinity": global_platform_node_pool_config["affinity"],
                    "tolerations": global_platform_node_pool_config["tolerations"],
                },
            },
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/postgresql/templates/statefulset.yaml", "charts/postgresql/templates/statefulset-slaves.yaml"],
        )

        assert len(docs) == 2
        spec = docs[0]["spec"]["template"]["spec"]
        assert spec["nodeSelector"]["role"] == "astromasterpostgresql"
        assert len(spec["affinity"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["postgresql"]["master"]["tolerations"]

        spec = docs[1]["spec"]["template"]["spec"]
        assert spec["nodeSelector"]["role"] == "astroslavepostgresql"
        assert len(spec["affinity"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["postgresql"]["slave"]["tolerations"]
