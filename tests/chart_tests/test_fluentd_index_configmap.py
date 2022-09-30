from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_registry_configmap(kube_version):
    """Test that helm renders an expected registry-configmap to validate
    regionendpoint flag."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=["charts/fluentd/templates/fluentd-index-template-configmap.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "ConfigMap"
    assert doc["apiVersion"] == "v1"
