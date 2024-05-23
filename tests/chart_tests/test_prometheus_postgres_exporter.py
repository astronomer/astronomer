import pytest

from tests import supported_k8s_versions, get_containers_by_name
from tests.chart_tests.helm_template_generator import render_chart


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
        assert c_by_name["prometheus-postgres-exporter"]["securityContext"] == {
            "runAsNonRoot": True
        }
