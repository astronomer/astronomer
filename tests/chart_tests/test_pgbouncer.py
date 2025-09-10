import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPGBouncerDeployment:
    def test_pgbouncer_deployment_defaults(self, kube_version):
        """Test pgbouncer deployment defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"pgbouncer": {"enabled": True}}},
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )

        assert len(docs) == 1
        deployment = docs[0]

        assert deployment["kind"] == "Deployment"
        assert deployment["metadata"]["name"] == "release-name-pgbouncer"

        c_by_name = get_containers_by_name(deployment)
        assert len(c_by_name) == 1
        assert c_by_name["pgbouncer"]["securityContext"] == {"readOnlyRootFilesystem": True, "runAsNonRoot": True}
        assert c_by_name["pgbouncer"]["resources"] == {
            "limits": {"cpu": "250m", "memory": "256Mi"},
            "requests": {"cpu": "250m", "memory": "256Mi"},
        }
        c_env = get_env_vars_dict(c_by_name["pgbouncer"]["env"])
        assert c_env["ADMIN_USERS"] == "postgres"
        assert c_env["AUTH_TYPE"] == "plain"

    def test_pgbouncer_deployment_custom_configurations(self, kube_version):
        """Test pgbouncer deployment with custom configurations."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"pgbouncer": {"enabled": True}},
                "pgbouncer": {
                    "env": {"foo_key": "foo_value", "bar_key": "bar_value"},
                    "securityContext": {
                        "snoopy": "dog",
                        "woodstock": "bird",
                    },
                },
            },
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert len(c_by_name) == 1
        assert c_by_name["pgbouncer"]["securityContext"] == {
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "snoopy": "dog",
            "woodstock": "bird",
        }

        c_env = get_env_vars_dict(c_by_name["pgbouncer"]["env"])
        assert c_env["ADMIN_USERS"] == "postgres"
        assert c_env["AUTH_TYPE"] == "plain"
        assert c_env["bar_key"] == "bar_value"
        assert c_env["foo_key"] == "foo_value"

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
            assert container["image"].startswith(private_registry), (
                f"Container named '{name}' does not use registry '{private_registry}': {container}"
            )
