from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import jmespath
import yaml


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_registry_configmap(kube_version):
    """Test that helm renders an expected registry-configmap to validate regionendpoint flag"""
    docs = render_chart(
        kube_version=kube_version,
        values={"astronomer": {"registry": {"s3": {"regionendpoint": "s3.us-south.cloud-object-storage.appdomain.cloud", "enabled": True}}}},
        show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "ConfigMap"
    assert doc["apiVersion"] == "v1"
    assert doc["metadata"]["name"] == "release-name-registry"
    assert (rc := yaml.safe_load(doc["data"]["config.yml"]))
    assert rc["storage"]["s3"]["regionendpoint"] == 's3.us-south.cloud-object-storage.appdomain.cloud'

