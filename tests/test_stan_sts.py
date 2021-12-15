from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_stan_statefulset(kube_version):
    """Test that helm renders a good statefulset template for astronomer stan."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=["charts/stan/templates/statefulset.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    containers = doc["spec"]["template"]["spec"]["containers"]
    c_by_name = {c["name"]: c for c in containers}
    assert doc["kind"] == "StatefulSet"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == "RELEASE-NAME-stan"
    assert {c["image"] for c in containers} == {
        "quay.io/astronomer/ap-nats-streaming:0.22.0-2",
        "quay.io/astronomer/ap-nats-exporter:0.9.0",
    }

    assert c_by_name["stan"]["livenessProbe"] == {
        "httpGet": {"path": "/streaming/serverz", "port": "monitor"},
        "initialDelaySeconds": 10,
        "timeoutSeconds": 5,
    }
    assert c_by_name["stan"]["readinessProbe"] == {
        "httpGet": {"path": "/streaming/serverz", "port": "monitor"},
        "initialDelaySeconds": 10,
        "timeoutSeconds": 5,
    }
