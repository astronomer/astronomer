from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import re


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusConfigConfigmap:
    show_only = ["charts/prometheus/templates/prometheus-config-configmap.yaml"]

    def test_prometheus_config_configmap(self, kube_version):
        """Validate the prometheus config configmap and its embedded data."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
        )

        assert len(docs) == 1

        doc = docs[0]

        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-prometheus-config"

    def test_prometheus_config_configmap_with_different_name_and_ns(self, kube_version):
        """Validate the prometheus config configmap does not conflate deployment name and namespace."""
        docs = render_chart(
            name="FOO-NAME",
            namespace="BAR-NS",
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "blackboxExporterEnabled": True,
                    "veleroEnabled": True,
                    "prometheusPostgresExporterEnabled": True,
                    "nodeExporterEnabled": True,
                },
                "tcpProbe": {"enabled": True},
            },
        )

        assert len(docs) == 1

        config_yaml = docs[0]["data"]["config"]
        assert re.search(r"http://FOO-NAME", config_yaml)
        assert not re.search(r"http://BAR-NS", config_yaml)
        assert re.search(r"\.BAR-NS:", config_yaml)
        assert not re.search(r"\.FOO-NAME:", config_yaml)
