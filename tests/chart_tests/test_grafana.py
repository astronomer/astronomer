import pytest

from tests.chart_tests.helm_template_generator import render_chart

from tests import supported_k8s_versions, get_containers_by_name


DEPLOYMENT_FILE = "charts/grafana/templates/grafana-deployment.yaml"


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestGrafanaDeployment:
    def test_deployment_should_render(self, kube_version):
        """Test that the grafana-deployment renders without error."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[DEPLOYMENT_FILE],
        )
        assert len(docs) == 1

    def test_deployment_should_render_extra_env(self, kube_version):
        """Test that helm renders extra environment variables to the grafana-
        deployment resource when provided."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"ssl": {"enabled": True}}},
            show_only=[DEPLOYMENT_FILE],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        grafana_container = None
        for container in doc["spec"]["template"]["spec"]["containers"]:
            if container["name"] == "grafana":
                grafana_container = container
                break
        assert grafana_container is not None
        assert len(grafana_container["env"]) == 3

        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"ssl": {"enabled": True}},
                "grafana": {
                    "extraEnvVars": [
                        {"name": "GF_SMTP_ENABLED", "value": "true"},
                        {"name": "GF_SMTP_HOST", "value": "smtp.astronomer.io"},
                    ]
                },
            },
            show_only=[DEPLOYMENT_FILE],
        )

        assert len(docs) == 1
        doc = docs[0]
        grafana_container = None
        for container in doc["spec"]["template"]["spec"]["containers"]:
            if container["name"] == "grafana":
                grafana_container = container
                break
        assert grafana_container is not None
        assert len(grafana_container["env"]) == 5

    def test_deployment_with_securitycontext_defaults(self, kube_version):
        """Test that the grafana-deployment renders with the expected securityContext."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[DEPLOYMENT_FILE],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=True)
        assert doc["kind"] == "Deployment"
        assert c_by_name["grafana"]["securityContext"] == {"runAsNonRoot": True}
        assert c_by_name["wait-for-db"]["securityContext"] == {"runAsNonRoot": True}
        assert c_by_name["bootstrapper"]["securityContext"] == {"runAsNonRoot": True}

    def test_deployment_with_securitycontext_overrides(self, kube_version):
        """Test that the grafana-deployment renders with the expected securityContext."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "grafana": {"securityContext": {"runAsNonRoot": True, "runAsUser": 467}}
            },
            show_only=[DEPLOYMENT_FILE],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        c_by_name = get_containers_by_name(doc, include_init_containers=True)
        assert c_by_name["grafana"]["securityContext"] == {
            "runAsNonRoot": True,
            "runAsUser": 467,
        }

        assert c_by_name["wait-for-db"]["securityContext"] == {
            "runAsNonRoot": True,
            "runAsUser": 467,
        }
        assert c_by_name["bootstrapper"]["securityContext"] == {
            "runAsNonRoot": True,
            "runAsUser": 467,
        }
