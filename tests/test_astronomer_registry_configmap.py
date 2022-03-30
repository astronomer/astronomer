from tests.helm_template_generator import render_chart
from . import supported_k8s_versions
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


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_registry_redirect(kube_version):
    """Test that helm renders redirect section in configmap of astronomer registry."""
    docs = render_chart(
        kube_version=kube_version,
        values={"astronomer": {"registry": {"redirectDisabled": True}}},
        show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    config_yml = doc["data"]["config.yml"]
    parsed_config_yml = yaml.safe_load(config_yml)
    redirectDisabled = parsed_config_yml["storage"]["redirect"]["disable"]
    assert doc["kind"] == "ConfigMap"
    assert redirectDisabled
