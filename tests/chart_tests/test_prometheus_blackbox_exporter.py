import pytest

from tests import supported_k8s_versions, get_containers_by_name
from tests.chart_tests.helm_template_generator import render_chart


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

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["metadata"]["name"] == "release-name-prometheus-blackbox-exporter"
        assert (
            doc["spec"]["selector"]["matchLabels"]["component"] == "blackbox-exporter"
        )
        assert (
            doc["spec"]["template"]["metadata"]["labels"]["app"]
            == "prometheus-blackbox-exporter"
        )

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

    def test_prometheus_blackbox_exporter_deployment_custom_resources(
        self, kube_version
    ):
        doc = render_chart(
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
        )[0]

        assert doc["kind"] == "Deployment"
        assert doc["metadata"]["name"] == "release-name-prometheus-blackbox-exporter"

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["blackbox-exporter"].get("resources"] == {
            "limits": {"cpu": "777m", "memory": "999Mi"},
            "requests": {"cpu": "666m", "memory": "888Mi"},
        }

    def test_prometheus_blackbox_exporter_deployment_custom_security_context(
        self, kube_version
    ):
        doc = render_chart(
            kube_version=kube_version,
            values={
                "prometheus-blackbox-exporter": {
                    "securityContext": {"runAsUser": 1000}
                },
            },
            show_only=["charts/prometheus-blackbox-exporter/templates/deployment.yaml"],
        )[0]

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["blackbox-exporter"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 1000,
        }
