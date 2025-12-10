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
            values={"global": {"postgresqlEnabled": True}},
            show_only=["charts/postgresql/templates/statefulset.yaml"],
        )

        assert len(docs) == 1
        sts = docs[0]
        self.postgresql_common_tests(sts)
        assert len(sts["spec"]["template"]["spec"]["containers"]) == 1
        containers = get_containers_by_name(doc=sts, include_init_containers=True)
        assert containers["release-name-postgresql"]["volumeMounts"] == [
            {"mountPath": "/tmp", "name": "tmp"},
            {"mountPath": "/opt/bitnami/postgresql/tmp", "name": "tmp", "subPath": "pg-tmp"},
            {"mountPath": "/opt/bitnami/postgresql/conf", "name": "pg-conf"},
            {"name": "data", "mountPath": "/bitnami/postgresql", "subPath": None},
        ]
        assert "persistentVolumeClaimRetentionPolicy" not in sts["spec"]

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
                    "postgresqlEnabled": True,
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
                "global": {"postgresqlEnabled": True},
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
                "global": {"postgresqlEnabled": True},
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
        values = {"global": {"platformNodePool": global_platform_node_pool_config, "postgresqlEnabled": True}}
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
            "global": {"postgresqlEnabled": True},
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
            "global": {"postgresqlEnabled": True},
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
