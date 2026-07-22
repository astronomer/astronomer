import subprocess

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

    def test_registry_configmap_name_override(self, kube_version):
        """registry.nameOverride drives the component label; resource name comes from fullname."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"registry": {"nameOverride": "custom-registry"}}},
            show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        # fullname falls back to "<release>-<name>" since the release name does not contain the override
        assert doc["metadata"]["name"] == "release-name-custom-registry"
        assert doc["metadata"]["labels"]["component"] == "custom-registry"

    def test_registry_configmap_fullname_override(self, kube_version):
        """registry.fullnameOverride drives the resource name without touching the component label."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"registry": {"fullnameOverride": "my-registry"}}},
            show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        assert doc["metadata"]["name"] == "my-registry"
        assert doc["metadata"]["labels"]["component"] == "registry"

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

    def test_registry_configmap_houston_event_url_cp_ha(self, kube_version):
        """CP-HA (PINF-1069): the registry's Houston notification URL must target the GLOBAL
        hostname under HA so it health-routes to the active control plane, not a pinned per-CP host.
        """
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "baseDomain": "cp01.example.com",
                    "plane": {"mode": "data"},
                    "controlPlaneHA": {"enabled": True, "globalBaseDomain": "example.com"},
                },
            },
            show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
        )
        assert len(docs) == 1
        config = yaml.safe_load(docs[0]["data"]["config.yml"])
        houston_endpoint = next(
            (endpoint for endpoint in config["notifications"]["endpoints"] if endpoint["name"] == "houston"),
            None,
        )
        assert houston_endpoint["url"] == "https://houston.example.com/v1/registry/events", (
            "registry notifications must target the global Houston hostname under CP-HA, not the per-CP baseDomain"
        )

    def test_registry_configmap_houston_event_url_cp_ha_missing_global_base_domain(self, kube_version):
        """CP-HA (PINF-1069): HA enabled but globalBaseDomain unset must hard-fail rather than
        silently pinning the registry notification URL to the per-CP baseDomain.
        """
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            render_chart(
                kube_version=kube_version,
                values={
                    "global": {
                        "baseDomain": "cp01.example.com",
                        "plane": {"mode": "data"},
                        "controlPlaneHA": {"enabled": True},
                    },
                },
                show_only=["charts/astronomer/templates/registry/registry-configmap.yaml"],
            )
        assert "globalBaseDomain is required" in exc_info.value.stderr.decode("utf-8")
