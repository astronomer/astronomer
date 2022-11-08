from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import yaml


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class Test_Registry_Configmap:
    def test_registry_configmap_with_s3Enabled(self, kube_version):
        """Test that helm renders an expected registry-configmap to validate
        regionendpoint flag."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "registry": {
                        "s3": {
                            "regionendpoint": "s3.us-south.cloud-object-storage.appdomain.cloud",
                            "enabled": True,
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert (rc := yaml.safe_load(doc["data"]["config.yml"]))
        assert (
            rc["storage"]["s3"]["regionendpoint"]
            == "s3.us-south.cloud-object-storage.appdomain.cloud"
        )

    def test_registry_configmap_with_logLevel_defaults(self, kube_version):
        """Test registry-configmap to validate log level defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"registry": {}}},
            show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert (rc := yaml.safe_load(doc["data"]["config.yml"]))
        assert rc["log"]["level"] == "info"

    def test_registry_configmap_with_logLevel_overrides(self, kube_version):
        """Test registry-configmap to validate log level defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"registry": {"logLevel": "debug"}}},
            show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert (rc := yaml.safe_load(doc["data"]["config.yml"]))
        assert rc["log"]["level"] == "debug"
