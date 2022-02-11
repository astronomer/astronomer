from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions, get_containers_by_name


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPostgresql:
    def test_postgresql_statefulset_defaults(self, kube_version):
        """Test postgresql statefulset is good with defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"postgresqlEnabled": True}},
            show_only=["charts/postgresql/templates/statefulset.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-postgresql"
        assert "initContainers" not in doc["spec"]["template"]["spec"]

    def test_postgresql_statefulset_with_volumePermissions_enabled(self, kube_version):
        """Test postgresql statefulset when volumePermissions init container is enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"postgresqlEnabled": True},
                "postgresql": {
                    "volumePermissions": {"enabled": True},
                    "persistence": {"enabled": True},
                },
            },
            show_only=["charts/postgresql/templates/statefulset.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-postgresql"
        assert "initContainers" in doc["spec"]["template"]["spec"]

    def test_postgresql_statefulset_with_private_registry_enabled(self, kube_version):
        """Test postgresql with privateRegistry=True."""
        repostiory = "private-repository.example.com"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        "repository": repostiory,
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
                assert container["image"].startswith(
                    repostiory
                ), f"Container named '{name}' does not use registry '{repostiory}': {container}"
