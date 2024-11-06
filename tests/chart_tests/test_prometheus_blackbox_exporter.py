import pytest

from tests import supported_k8s_versions, get_containers_by_name
from tests.chart_tests.helm_template_generator import render_chart


def common_blackbox_exporter_tests(docs):
    """Test common asserts for prometheus blackbox exporter."""
    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "Deployment"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == "release-name-prometheus-blackbox-exporter"
    assert doc["spec"]["selector"]["matchLabels"]["component"] == "blackbox-exporter"
    assert doc["spec"]["template"]["metadata"]["labels"]["app"] == "prometheus-blackbox-exporter"


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusBlackBoxExporterDeployment:
    def test_prometheus_blackbox_exporter_service_defaults(self, kube_version):
        values = {
            "global": {
                "prometheusBlackboxExporterEnabled": True,
            }
        }

        docs = render_chart(
            values=values,
            kube_version=kube_version,
            show_only=["charts/prometheus-blackbox-exporter/templates/service.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Service"
        assert doc["metadata"]["name"] == "release-name-prometheus-blackbox-exporter"
        assert doc["spec"]["selector"]["component"] == "blackbox-exporter"
        assert doc["spec"]["type"] == "ClusterIP"
        assert doc["spec"]["ports"] == [
            {
                "port": 9115,
                "protocol": "TCP",
                "name": "http",
                "appProtocol": "http",
            }
        ]

    def test_prometheus_blackbox_exporter_deployment_defaults(self, kube_version):

        values = {
            "global": {
                "prometheusBlackboxExporterEnabled": True,
            }
        }

        docs = render_chart(
            values=values,
            kube_version=kube_version,
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml"],
        )

        common_blackbox_exporter_tests(docs)
        doc = docs[0]

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["blackbox-exporter"]["resources"] == {
            "limits": {"cpu": "100m", "memory": "200Mi"},
            "requests": {"cpu": "50m", "memory": "70Mi"},
        }
        assert c_by_name["blackbox-exporter"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "capabilities": {"drop": ["ALL"]},
        }
        spec = doc["spec"]["template"]["spec"]
        assert spec["nodeSelector"] == {}
        assert spec["affinity"] == {}
        assert spec["tolerations"] == []

    def test_prometheus_blackbox_exporter_deployment_custom_resources(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "prometheus-blackbox-exporter": {
                    "resources": {
                        "limits": {"cpu": "777m", "memory": "999Mi"},
                        "requests": {"cpu": "666m", "memory": "888Mi"},
                    }
                },
                "global": {
                "prometheusBlackboxExporterEnabled": True,
            }
            },
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml"],
        )

        common_blackbox_exporter_tests(docs)
        c_by_name = get_containers_by_name(docs[0])
        assert c_by_name["blackbox-exporter"].get("resources") == {
            "limits": {"cpu": "777m", "memory": "999Mi"},
            "requests": {"cpu": "666m", "memory": "888Mi"},
        }

    def test_prometheus_blackbox_exporter_deployment_custom_security_context(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "prometheus-blackbox-exporter": {"securityContext": {"runAsUser": 1000}},
                "global": {
                "prometheusBlackboxExporterEnabled": True,
            },
            },
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml"],
        )
        common_blackbox_exporter_tests(docs)
        c_by_name = get_containers_by_name(docs[0])
        assert c_by_name["blackbox-exporter"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 1000,
        }

    def test_prometheus_blackbox_exporter_deployment_global_platform_nodepool(self, kube_version, global_platform_node_pool_config):
        """Test that blackbox exporter renders proper nodeSelector, affinity,
        and tolerations with global overrides"""
        values = {
            "global": {
                "platformNodePool": global_platform_node_pool_config,
                "prometheusBlackboxExporterEnabled": True,
            }
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml"],
        )
        common_blackbox_exporter_tests(docs)
        spec = docs[0]["spec"]["template"]["spec"]
        assert len(spec["nodeSelector"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["global"]["platformNodePool"]["tolerations"]

    def test_prometheus_blackbox_exporter_defaults_with_subchart_overrides(self, kube_version, global_platform_node_pool_config):
        """Test that blackbox exporter renders proper nodeSelector, affinity,
        and tolerations with sunchart overrides"""
        global_platform_node_pool_config["nodeSelector"] = {"role": "astro-prometheus-blackbox-exporter"}
        values = {"prometheus-blackbox-exporter": global_platform_node_pool_config,
                  "global": {
                "prometheusBlackboxExporterEnabled": True,
            },
            }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml"],
        )
        spec = docs[0]["spec"]["template"]["spec"]
        assert len(spec["nodeSelector"]) == 1
        assert len(spec["affinity"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["nodeSelector"] == values["prometheus-blackbox-exporter"]["nodeSelector"]
        assert spec["tolerations"] == values["prometheus-blackbox-exporter"]["tolerations"]

    def test_prometheus_blackbox_exporter_enabled_flag(self, kube_version):
        """Test that the prometheusBlackboxExporter.enabled flag controls resource creation."""
        values = {
            "global": {
                "prometheusBlackboxExporterEnabled": True,
            }
        }

        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml", "charts/prometheus-blackbox-exporter/templates/configmap.yaml",
                       "charts/prometheus-blackbox-exporter/templates/service.yaml" ],
        )

        assert len(docs) == 3
