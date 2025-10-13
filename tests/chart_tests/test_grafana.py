import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart

DEPLOYMENT_FILE = "charts/grafana/templates/grafana-deployment.yaml"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
@pytest.mark.parametrize("plane_mode,docs_count", [("control", 1), ("unified", 1), ("data", 0)])
def test_deployment_should_render(kube_version, plane_mode, docs_count):
    """Test that the grafana-deployment renders without error."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=[DEPLOYMENT_FILE],
        values={"global": {"plane": {"mode": plane_mode}}},
    )
    assert len(docs) == docs_count


@pytest.mark.parametrize("plane_mode", ["control", "unified"])
@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_deployment_should_render_extra_env(kube_version, plane_mode):
    """Test that helm renders extra environment variables to the grafana-deployment resource when provided."""
    docs = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "plane": {"mode": plane_mode},
                "ssl": {
                    "enabled": True,
                },
            },
        },
        show_only=[DEPLOYMENT_FILE],
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "Deployment"
    grafana_container = next(
        (container for container in doc["spec"]["template"]["spec"]["containers"] if container["name"] == "grafana"),
        None,
    )
    assert grafana_container is not None
    assert len(grafana_container["env"]) == 3

    docs = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "plane": {"mode": plane_mode},
                "ssl": {"enabled": True},
            },
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
    grafana_container = next(
        (container for container in doc["spec"]["template"]["spec"]["containers"] if container["name"] == "grafana"),
        None,
    )
    assert grafana_container is not None
    assert len(grafana_container["env"]) == 5


@pytest.mark.parametrize("plane_mode", ["control", "unified"])
@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_deployment_with_securitycontext_defaults(kube_version, plane_mode):
    """Test that the grafana-deployment renders with the expected securityContext."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=[DEPLOYMENT_FILE],
    )

    assert len(docs) == 1
    doc = docs[0]
    c_by_name = get_containers_by_name(doc, include_init_containers=True)
    assert doc["kind"] == "Deployment"
    assert c_by_name["grafana"]["securityContext"] == {"readOnlyRootFilesystem": True, "runAsNonRoot": True}
    assert c_by_name["wait-for-db"]["securityContext"] == {"readOnlyRootFilesystem": True, "runAsNonRoot": True}
    assert c_by_name["bootstrapper"]["securityContext"] == {"readOnlyRootFilesystem": True, "runAsNonRoot": True}


@pytest.mark.parametrize("plane_mode", ["control", "unified"])
@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_deployment_with_securitycontext_overrides(kube_version, plane_mode):
    """Test that the grafana-deployment renders with the expected securityContext."""
    docs = render_chart(
        kube_version=kube_version,
        values={
            "global": {"plane": {"mode": plane_mode}},
            "grafana": {"securityContext": {"runAsNonRoot": True, "runAsUser": 467}},
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
        "readOnlyRootFilesystem": True,
    }

    assert c_by_name["wait-for-db"]["securityContext"] == {
        "runAsNonRoot": True,
        "runAsUser": 467,
        "readOnlyRootFilesystem": True,
    }
    assert c_by_name["bootstrapper"]["securityContext"] == {
        "runAsNonRoot": True,
        "runAsUser": 467,
        "readOnlyRootFilesystem": True,
    }


@pytest.mark.parametrize("plane_mode", ["control", "unified"])
@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_grafana_init_containers_disabled_with_custom_secret_name(kube_version, plane_mode):
    """Test that the grafana deployment init containers disabled."""
    docs = render_chart(
        kube_version=kube_version,
        values={"global": {"plane": {"mode": plane_mode}}, "grafana": {"backendSecretName": "grafanabackend"}},
        show_only=[DEPLOYMENT_FILE],
    )
    assert len(docs) == 1
    doc = docs[0]
    spec = doc["spec"]["template"]["spec"]
    assert "initContainers" not in spec
    assert "default" == spec["serviceAccountName"]
    c_by_name = get_containers_by_name(doc, include_init_containers=False)
    assert {
        "name": "GF_DATABASE_URL",
        "valueFrom": {"secretKeyRef": {"name": "grafanabackend", "key": "connection"}},
    } in c_by_name["grafana"]["env"]
