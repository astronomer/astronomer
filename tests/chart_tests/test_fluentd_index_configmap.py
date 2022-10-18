from tests.chart_tests.helm_template_generator import render_chart
import pytest
import yaml
from tests import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_fluentd_index_configmap(kube_version):
    """Test to validate  fluentd index configmap."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=["charts/fluentd/templates/fluentd-index-template-configmap.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "ConfigMap"
    assert doc["apiVersion"] == "v1"
    assert doc["metadata"]["name"] == "release-name-fluentd-index-template-configmap"
    index_cm = yaml.safe_load(doc["data"]["index_template.json"])
    assert index_cm == {
        "index_patterns": ["fluentd.*"],
        "mappings": {"properties": {"date_nano": {"type": "date_nanos"}}},
    }
