import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestStatefulSetsAnnotations:
    def test_sts_with_default_annotations(self, kube_version):
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

    def test_es_sts_with_overridden_annotations(self, kube_version):
        """Test all sts for the volume claim templates annotations"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "common": {
                        "persistence": {
                            "annotations": {
                                "astro.io/elastic": "master-sts",
                                "storage": "astro",
                            }
                        }
                    }
                }
            },
            show_only=[
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
            ],
        )
        assert len(docs) == 2
        for doc in docs:
            assert {"astro.io/elastic": "master-sts", "storage": "astro"} == doc[
                "spec"
            ]["volumeClaimTemplates"][0]["metadata"]["annotations"]

    def test_prometheus_sts_with_overridden_annotations(self, kube_version):
        """Test all sts for the volume claim templates annotations"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "prometheus": {
                    "persistence": {
                        "annotations": {
                            "astro.io/monitoring": "prom-sts",
                            "annotation": "astro-test",
                        }
                    }
                }
            },
            show_only=[
                "charts/prometheus/templates/prometheus-statefulset.yaml",
            ],
        )
        assert len(docs) == 1
        for doc in docs:
            assert {
                "annotation": "astro-test",
                "astro.io/monitoring": "prom-sts",
            } == doc["spec"]["volumeClaimTemplates"][0]["metadata"]["annotations"]

    def test_registry_sts_with_overridden_annotations(self, kube_version):
        """Test all sts for the volume claim templates annotations"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "registry": {
                        "persistence": {
                            "annotations": {
                                "astro.io/registry": "registry-sts",
                                "annotation": "registry-test",
                            }
                        }
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/registry/registry-statefulset.yaml",
            ],
        )
        assert len(docs) == 1
        for doc in docs:
            assert {
                "annotation": "registry-test",
                "astro.io/registry": "registry-sts",
            } == doc["spec"]["volumeClaimTemplates"][0]["metadata"]["annotations"]

    def test_stan_sts_with_overridden_annotations(self, kube_version):
        """Test all sts for the volume claim templates annotations"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "stan": {
                    "persistence": {
                        "annotations": {
                            "astro.io/stan": "stan-sts",
                            "annotation": "stan-test",
                        }
                    }
                }
            },
            show_only=[
                "charts/stan/templates/statefulset.yaml",
            ],
        )
        assert len(docs) == 1
        for doc in docs:
            # print(doc["spec"]["volumeClaimTemplates"][0]["metadata"]["annotations"])
            assert {"annotation": "stan-test", "astro.io/stan": "stan-sts"} == doc[
                "spec"
            ]["volumeClaimTemplates"][0]["metadata"]["annotations"]
