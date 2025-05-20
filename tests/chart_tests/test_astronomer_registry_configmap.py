import re

import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestRegistryConfigmap:
    def test_astronomer_registry_configmap_defaults(self, kube_version):
        """Test that helm renders a good configmap template for astronomer
        registry."""
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

    def test_astronomer_registry_redirect_disabled(self, kube_version):
        """Test that helm renders astronomer registry configmap template with
        redirect disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"registry": {"redirect": {"disable": True}}}},
            show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        parsed_config_yml = yaml.safe_load(doc["data"]["config.yml"])
        assert parsed_config_yml["storage"]["redirect"]["disable"]

    def test_astronomer_registry_auth_disabled(self, kube_version):
        """Test that auth section is disabled when enableInsecureAuth is set to True"""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"registry": {"enableInsecureAuth": True}}},
            show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
        )
        assert len(docs) == 1
        config_yaml = yaml.safe_load(docs[0]["data"]["config.yml"])
        assert not config_yaml.get("auth")
