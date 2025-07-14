import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusPostgresExporter:
    def test_prometheus_postgres_exporter_service_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "prometheusPostgresExporterEnabled": True,
                },
            },
            show_only=[
                "charts/prometheus-postgres-exporter/templates/service.yaml",
                "charts/prometheus-postgres-exporter/templates/deployment.yaml",
                "charts/prometheus-postgres-exporter/templates/configmap.yaml",
                "charts/prometheus-postgres-exporter/templates/serviceaccount.yaml",
            ],
        )
        assert len(docs) == 4
        doc = docs[0]
        assert doc["kind"] == "Service"
        assert doc["metadata"]["name"] == "release-name-postgresql-exporter"
        assert doc["spec"]["selector"]["app"] == "prometheus-postgres-exporter"
        assert doc["spec"]["type"] == "ClusterIP"
        assert doc["spec"]["ports"] == [
            {
                "port": 80,
                "targetPort": "http",
                "protocol": "TCP",
                "name": "http",
                "appProtocol": "tcp",
            }
        ]
        c_by_name = get_containers_by_name(docs[1])
        assert c_by_name["prometheus-postgres-exporter"]
        assert c_by_name["prometheus-postgres-exporter"]["resources"] == {
            "limits": {"cpu": "100m", "memory": "128Mi"},
            "requests": {"cpu": "10m", "memory": "128Mi"},
        }
        assert c_by_name["prometheus-postgres-exporter"]["livenessProbe"] == {
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
            "tcpSocket": {"port": 9187},
        }
        assert c_by_name["prometheus-postgres-exporter"]["readinessProbe"] == {
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
            "tcpSocket": {"port": 9187},
        }
        assert c_by_name["prometheus-postgres-exporter"]["securityContext"] == {
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
        }
        spec = docs[1]["spec"]["template"]["spec"]
        assert spec["nodeSelector"] == {}
        assert spec["affinity"] == {}
        assert spec["tolerations"] == []

    def test_prometheus_postgres_exporter_with_global_platform_nodepool(self, kube_version, global_platform_node_pool_config):
        """Test that postgres exporter renders proper nodeSelector, affinity,
        and tolerations with global values."""
        values = {
            "global": {
                "prometheusPostgresExporterEnabled": True,
                "platformNodePool": global_platform_node_pool_config,
            }
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/prometheus-postgres-exporter/templates/deployment.yaml"],
        )
        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert len(spec["nodeSelector"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["global"]["platformNodePool"]["tolerations"]

    def test_prometheus_postgres_exporter_defaults_with_subchart_overrides(self, kube_version, global_platform_node_pool_config):
        """Test that postgres exporter renders proper nodeSelector, affinity,
        and tolerations with subchart overrides."""

        global_platform_node_pool_config["nodeSelector"] = {"role": "astro-prometheus-postgres-exporter"}
        values = {
            "global": {"prometheusPostgresExporterEnabled": True},
            "prometheus-postgres-exporter": global_platform_node_pool_config,
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/prometheus-postgres-exporter/templates/deployment.yaml"],
        )
        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert len(spec["nodeSelector"]) == 1
        assert len(spec["affinity"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["nodeSelector"] == values["prometheus-postgres-exporter"]["nodeSelector"]
        assert spec["tolerations"] == values["prometheus-postgres-exporter"]["tolerations"]
