from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import jmespath


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_commander_deployment(kube_version):
    """Test that helm renders a good deployment template for astronomer/commander."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "Deployment"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == "RELEASE-NAME-commander"
    assert "quay.io/astronomer/ap-commander:0.25.2" in jmespath.search(
        "spec.template.spec.containers[*].image", doc
    )
