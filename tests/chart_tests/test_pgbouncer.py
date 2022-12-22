import pytest

from tests import get_containers_by_name, supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPGBouncerDeployment:
    def test_pgbouncer_deployment_default_resources(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"pgbouncer": {"enabled": True}}},
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "Deployment"
        assert doc["metadata"]["name"] == "release-name-pgbouncer"

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["pgbouncer"]
        assert c_by_name["pgbouncer"]["resources"] == {
            "limits": {"cpu": "250m", "memory": "256Mi"},
            "requests": {"cpu": "250m", "memory": "256Mi"},
        }
        assert not doc["spec"]["template"]["spec"].get("env")

    def test_custom_environment(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "pgbouncer": {
                        "enabled": True,
                    }
                },
                "pgbouncer": {"env": {"foo_key": "foo_value", "bar_key": "bar_value"}},
            },
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )[0]

        c_env = doc["spec"]["template"]["spec"]["containers"][0]["env"]
        assert {"name": "bar_key", "value": "bar_value"} in c_env
        assert {"name": "foo_key", "value": "foo_value"} in c_env

    def test_custom_labels(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "pgbouncer": {
                        "enabled": True,
                        "extraLabels": {"test_label": "test_label1"},
                    }
                },
            },
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )[0]

        labels = doc["spec"]["template"]["metadata"]["labels"]
        assert labels.get("test_label") == "test_label1"

    def test_pgbouncer_deployment_with_private_registry(self, kube_version):
        """Test that pgbouncer deployment properly uses the private registry
        images."""
        private_registry = "private-registry.example.com"
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
            values={
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        "repository": private_registry,
                    },
                    "pgbouncer": {"enabled": True},
                }
            },
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=True)

        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"

        for name, container in c_by_name.items():
            assert container["image"].startswith(
                private_registry
            ), f"Container named '{name}' does not use registry '{private_registry}': {container}"
