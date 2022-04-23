import re

import pytest
import yaml

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_registry_configmap_defaults(kube_version):
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
    assert "redirect" not in parsed_config_yml["storage"]


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_registry_redirect_disabled(kube_version):
    """Test that helm renders astronomer registry configmap template with redirect disabled."""
    docs = render_chart(
        kube_version=kube_version,
        values={"astronomer": {"registry": {"redirect": {"disable": True}}}},
        show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    parsed_config_yml = yaml.safe_load(doc["data"]["config.yml"])
    assert parsed_config_yml["storage"]["redirect"]["disable"]
