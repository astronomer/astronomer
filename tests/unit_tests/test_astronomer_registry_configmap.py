from tests.unit_tests.helm_template_generator import render_chart
from tests import supported_k8s_versions
import pytest
import yaml
import re


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_registry_configmap(kube_version):
    """Test that helm renders a good configmap template for astronomer registry."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    config_yml = doc["data"]["config.yml"]
    parsed_config_yml = yaml.safe_load(config_yml)
    timeout = parsed_config_yml["notifications"]["endpoints"][0]["timeout"]
    assert doc["kind"] == "ConfigMap"
    assert doc["apiVersion"] == "v1"
    assert bool(re.match("[+]?\\d+s", timeout))
