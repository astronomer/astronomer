from tests.helm_template_generator import render_chart
from . import supported_k8s_versions
import pytest


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusBlackboxExporter:
    def test_prometheus_alerts_configmap(self, kube_version):
        """Validate the prometheus alerts configmap and its embedded data."""
        show_only = ["charts/prometheus/templates/prometheus-alerts-configmap.yaml"]
        docs = render_chart(
            kube_version=kube_version,
            show_only=show_only,
        )

        assert len(docs) == 1

        doc = docs[0]

        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-prometheus-alerts"
