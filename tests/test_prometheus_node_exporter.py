from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions, get_containers_by_name


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusNodeExporterDaemonset:
    def test_prometheus_node_exporter_daemonset_default_resources(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/prometheus-node-exporter/templates/daemonset.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "DaemonSet"
        assert doc["metadata"]["name"] == "release-name-prometheus-node-exporter"

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["node-exporter"]
        assert c_by_name["node-exporter"]["resources"] == {
            "limits": {"cpu": "100m", "memory": "128Mi"},
            "requests": {"cpu": "10m", "memory": "128Mi"},
        }

    def test_prometheus_node_exporter_daemonset_custom_resources(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "prometheus-node-exporter": {
                    "resources": {
                        "limits": {"cpu": "777m", "memory": "999Mi"},
                        "requests": {"cpu": "666m", "memory": "888Mi"},
                    }
                },
            },
            show_only=["charts/prometheus-node-exporter/templates/daemonset.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "DaemonSet"
        assert doc["metadata"]["name"] == "release-name-prometheus-node-exporter"

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["node-exporter"]
        assert c_by_name["node-exporter"]["resources"] == {
            "limits": {"cpu": "777m", "memory": "999Mi"},
            "requests": {"cpu": "666m", "memory": "888Mi"},
        }
