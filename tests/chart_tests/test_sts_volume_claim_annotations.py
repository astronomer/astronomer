import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestElasticSearch:
    def test_elasticsearch_with_default_annotations(self, kube_version):
        """Test all sts for the volume claim templates annotations"""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
                "charts/alertmanager/templates/alertmanager-statefulset.yaml",
                "charts/astronomer/templates/registry/registry-statefulset.yaml",
                "charts/prometheus/templates/prometheus-statefulset.yaml",
                "charts/stan/templates/statefulset.yaml",
            ],
        )

        assert len(docs) == 6
        for doc in docs:
            if "annotations" in doc["spec"]["volumeClaimTemplates"][0]["metadata"]:
                assert doc["spec"]["volumeClaimTemplates"][0]["metadata"]["annotations"]
