from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import jmespath


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestElasticSearch:
    def test_elasticsearch_with_sysctl_defaults(self, kube_version):
        """Test  ElasticSearch with sysctl config/values.yaml."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
                "charts/elasticsearch/templates/client/es-client-deployment.yaml",
            ],
        )

        default_max_map_count = "262144"
        assert len(docs) == 3

        # elasticsearch master
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert "sysctl" == jmespath.search(
            "spec.template.spec.initContainers[0].name", docs[0]
        )
        assert any(
            default_max_map_count in arg
            for args in jmespath.search(
                "spec.template.spec.initContainers[*].command", doc
            )
            for arg in args
        )

        # elasticsearch data
        doc = docs[1]
        assert doc["kind"] == "StatefulSet"
        assert "sysctl" == jmespath.search(
            "spec.template.spec.initContainers[0].name", docs[1]
        )
        assert any(
            default_max_map_count in arg
            for args in jmespath.search(
                "spec.template.spec.initContainers[*].command", doc
            )
            for arg in args
        )

        # elasticsearch client
        doc = docs[2]
        assert doc["kind"] == "Deployment"
        assert "sysctl" == jmespath.search(
            "spec.template.spec.initContainers[0].name", docs[2]
        )
        assert any(
            default_max_map_count in arg
            for args in jmespath.search(
                "spec.template.spec.initContainers[*].command", doc
            )
            for arg in args
        )

    def test_elasticsearch_with_sysctl_disabled(self, kube_version):
        """Test ElasticSearch master,data and client with sysctl config/values.yaml."""
        docs = render_chart(
            kube_version=kube_version,
            values={"elasticsearch": {"sysctlInitContainer": {"enabled": False}}},
            show_only=[
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
                "charts/elasticsearch/templates/client/es-client-deployment.yaml",
            ],
        )

        assert len(docs) == 3
        for doc_ids in range(len(docs)):
            assert jmespath.search("spec.template.spec.initContainers", docs[0]) is None

    def test_elasticsearch_securitycontext_defaults(self, kube_version):
        """Test  ElasticSearch master, data and client with securitycontext default values"""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
                "charts/elasticsearch/templates/client/es-client-deployment.yaml",
            ],
        )
        assert len(docs) == 3
        for doc_ids in range(len(docs)):
            assert docs[doc_ids]["spec"]["template"]["spec"]["securityContext"] == {
                "fsGroup": 1000
            }
