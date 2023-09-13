import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestKibana:
    def test_kibana_index_defaults(self, kube_version):
        """Test kibana Service with index defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/kibana/templates/kibana-default-index-cronjob.yaml",
            ],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Job"
        assert doc["apiVersion"] == "batch/v1"
        assert doc["metadata"]["name"] == "release-name-kibana-default-index-job"
        assert (
            "fluentd.*"
            in doc["spec"]["template"]["spec"]["containers"][0]["command"][2]
        )

    def test_kibana_index_with_logging_sidecar(self, kube_version):
        """Test kibana Service with logging sidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"loggingSidecar": {"enabled": True}}},
            show_only=[
                "charts/kibana/templates/kibana-default-index-cronjob.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Job"
        assert doc["apiVersion"] == "batch/v1"
        assert doc["metadata"]["name"] == "release-name-kibana-default-index-job"
        assert (
            "vector.*" in doc["spec"]["template"]["spec"]["containers"][0]["command"][2]
        )
