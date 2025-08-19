import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class Test_Registry_Configmap:
    def test_registry_configmap_with_s3_enabled(self, kube_version):
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
        assert (
            yaml.safe_load(doc["data"]["config.yml"])["storage"]["s3"]["regionendpoint"]
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
        assert yaml.safe_load(doc["data"]["config.yml"])["log"]["level"] == "info"

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
        assert yaml.safe_load(doc["data"]["config.yml"])["log"]["level"] == "debug"

    def test_registry_configmap_with_houston_event_url(self, kube_version):
        """Test that helm renders registry-configmap with correct Houston event URL for notifications."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"baseDomain": "astronomer.example.com", "plane": {"mode": "data"}},
                "astronomer": {
                    "houston": {"eventUrl": "/v1/authorization"},
                },
            },
            show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-registry"

        config = yaml.safe_load(doc["data"]["config.yml"])

        assert config.get("notifications", {}).get("endpoints", [])

        houston_endpoint = next(
            (endpoint for endpoint in config["notifications"]["endpoints"] if endpoint["name"] == "houston"),
            None,
        )
        assert houston_endpoint["url"] == "https://houston.example.com/v1/registry/events"
