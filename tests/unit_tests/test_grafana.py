import pytest

from tests.unit_tests.helm_template_generator import render_chart

from tests import supported_k8s_versions


DEPLOYMENT_FILE = "charts/grafana/templates/grafana-deployment.yaml"


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_deployment_should_render(kube_version):
    """Test that the grafana-deployment renders without error."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=[DEPLOYMENT_FILE],
    )
    assert len(docs) == 1


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_deployment_should_render_extra_env(kube_version):
    """Test that helm renders extra environment variables to the grafana-deployment resource when provided."""
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
