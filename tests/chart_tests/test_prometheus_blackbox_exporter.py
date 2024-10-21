import pytest

from tests import supported_k8s_versions, get_containers_by_name, global_platform_node_pool_config
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
        docs = render_chart(
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
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml"],
        )

        common_blackbox_exporter_tests(docs)
        doc = docs[0]
        assert doc["spec"]["template"]["spec"]["nodeSelector"] == {}
        assert doc["spec"]["template"]["spec"]["affinity"] == {}
        assert doc["spec"]["template"]["spec"]["tolerations"] == []

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
            },
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml"],
        )

        common_blackbox_exporter_tests(docs)
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        assert c_by_name["blackbox-exporter"].get("resources") == {
            "limits": {"cpu": "777m", "memory": "999Mi"},
            "requests": {"cpu": "666m", "memory": "888Mi"},
        }

    def test_prometheus_blackbox_exporter_deployment_custom_security_context(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "prometheus-blackbox-exporter": {"securityContext": {"runAsUser": 1000}},
            },
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml"],
        )
        common_blackbox_exporter_tests(docs)
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        assert c_by_name["blackbox-exporter"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 1000,
        }

    def test_prometheus_blackbox_exporter_deployment_global_platform_nodepool(self, kube_version):
        """Test that blackbox exporter renders proper nodeSelector, affinity,
        and tolerations with global overrides"""
        values = {
            "global": {
                "platformNodePool": global_platform_node_pool_config,
            }
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml"],
        )
        common_blackbox_exporter_tests(docs)
        doc = docs[0]
        assert len(doc["spec"]["template"]["spec"]["nodeSelector"]) == 1
        assert len(doc["spec"]["template"]["spec"]["tolerations"]) > 0
        assert doc["spec"]["template"]["spec"]["tolerations"] == values["global"]["platformNodePool"]["tolerations"]

    def test_prometheus_blackbox_exporter_defaults_with_subchart_overrides(self, kube_version):
        """Test that blackbox exporter renders proper nodeSelector, affinity,
        and tolerations with sunchart overrides"""
        values = {
            "prometheus-blackbox-exporter": {
                "nodeSelector": {"role": "astro-prometheus-blackbox-exporter"},
                "affinity": {
                    "nodeAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": {
                            "nodeSelectorTerms": [
                                {
                                    "matchExpressions": [
                                        {
                                            "key": "astronomer.io/multi-tenant",
                                            "operator": "In",
                                            "values": ["false"],
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                },
                "tolerations": [
                    {
                        "effect": "NoSchedule",
                        "key": "astronomer",
                        "operator": "Exists",
                    }
                ],
            }
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml"],
        )
        doc = docs[0]
        assert len(doc["spec"]["template"]["spec"]["nodeSelector"]) == 1
        assert len(doc["spec"]["template"]["spec"]["affinity"]) == 1
        assert len(doc["spec"]["template"]["spec"]["tolerations"]) > 0
        doc["spec"]["template"]["spec"]["nodeSelector"] == "astro-prometheus-blackbox-exporter"
        assert doc["spec"]["template"]["spec"]["tolerations"] == values["prometheus-blackbox-exporter"]["tolerations"]
