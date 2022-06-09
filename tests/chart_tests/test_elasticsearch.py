import jmespath
import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestElasticSearch:
    def test_elasticsearch_with_sysctl_defaults(self, kube_version):
        """Test ElasticSearch with sysctl config/values.yaml."""
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
        """Test ElasticSearch master, data and client with sysctl config/values.yaml."""
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
        for doc in docs:
            assert not doc["spec"]["template"]["spec"]["initContainers"]

    def test_elasticsearch_fsgroup_defaults(self, kube_version):
        """Test ElasticSearch master, data and client with fsGroup default values"""
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
        for doc in docs:
            assert doc["spec"]["template"]["spec"]["securityContext"] == {
                "fsGroup": 1000
            }

    def test_elasticsearch_securitycontext_defaults(self, kube_version):
        """Test ElasticSearch master, data with securityContext default values"""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
            ],
        )
        assert len(docs) == 2
        for doc in docs:
            pod_data = doc["spec"]["template"]["spec"]["containers"][0]
            assert pod_data["securityContext"]["capabilities"]["drop"] == ["ALL"]
            assert pod_data["securityContext"]["runAsNonRoot"] is True
            assert pod_data["securityContext"]["runAsUser"] == 1000

    def test_elasticsearch_securitycontext_overrides(self, kube_version):
        """Test ElasticSearch master, data with securityContext custom values"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "securityContext": {
                        "capabilities": {"add": ["IPC_LOCK"]},
                        "runAsNonRoot": True,
                        "runAsUser": 1001,
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
            pod_data = doc["spec"]["template"]["spec"]["containers"][0]
            assert pod_data["securityContext"]["capabilities"]["add"] == ["IPC_LOCK"]
            assert pod_data["securityContext"]["runAsNonRoot"] is True
            assert pod_data["securityContext"]["runAsUser"] == 1001

    def test_nginx_es_client_network_selector_defaults(self, kube_version):
        """Test Nginx ES Service with NetworkPolicy defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/nginx/nginx-es-ingress-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert "NetworkPolicy" == doc["kind"]
        assert [
            {
                "namespaceSelector": {},
                "podSelector": {
                    "matchLabels": {"tier": "airflow", "component": "webserver"}
                },
            },
        ] == doc["spec"]["ingress"][0]["from"]

    def test_nginx_es_client_network_selector_with_logging_sidecar_enabled(
        self, kube_version
    ):
        """Test Nginx ES Service with NetworkPolicies."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"loggingSidecar": {"enabled": True}}},
            show_only=[
                "charts/elasticsearch/templates/nginx/nginx-es-ingress-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert "NetworkPolicy" == doc["kind"]
        assert [
            {
                "namespaceSelector": {},
                "podSelector": {
                    "matchLabels": {"tier": "airflow", "component": "webserver"}
                },
            },
            {
                "namespaceSelector": {},
                "podSelector": {
                    "matchLabels": {"component": "scheduler", "tier": "airflow"}
                },
            },
            {
                "namespaceSelector": {},
                "podSelector": {
                    "matchLabels": {"component": "worker", "tier": "airflow"}
                },
            },
            {
                "namespaceSelector": {},
                "podSelector": {
                    "matchLabels": {"component": "triggerer", "tier": "airflow"}
                },
            },
        ] == doc["spec"]["ingress"][0]["from"]

    def test_nginx_es_index_pattern_defaults(self, kube_version):
        """Test External Elasticsearch Service Index Pattern Search defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/nginx/nginx-es-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        es_index = doc["data"]["nginx.conf"]
        assert doc["kind"] == "ConfigMap"
        assert "fluentd.$remote_user.*/$1" in es_index

    def test_nginx_es_index_pattern_with_sidecar_logging_enabled(self, kube_version):
        """Test Nginx ES Service Index Pattern Search with sidecar logging."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"loggingSidecar": {"enabled": True}}},
            show_only=[
                "charts/elasticsearch/templates/nginx/nginx-es-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        es_index = doc["data"]["nginx.conf"]
        assert doc["kind"] == "ConfigMap"
        assert "vector.$remote_user.*/$1" in es_index

    def test_elasticsearch_exporter_securitycontext_defaults(self, kube_version):
        """Test ElasticSearch Exporter with securityContext default values"""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/exporter/es-exporter-deployment.yaml"
            ],
        )
        assert len(docs) == 1
        doc = docs[0]
        pod_data = doc["spec"]["template"]["spec"]
        assert pod_data["securityContext"]["runAsNonRoot"] is True
        assert pod_data["securityContext"]["runAsUser"] == 1000

    def test_elasticsearch_exporter_securitycontext_overrides(self, kube_version):
        """Test ElasticSearch Exporter with securityContext default values"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "exporter": {
                        "securityContext": {"runAsNonRoot": True, "runAsUser": 2000}
                    }
                }
            },
            show_only=[
                "charts/elasticsearch/templates/exporter/es-exporter-deployment.yaml"
            ],
        )
        assert len(docs) == 1
        doc = docs[0]
        pod_data = doc["spec"]["template"]["spec"]
        assert pod_data["securityContext"]["runAsNonRoot"] is True
        assert pod_data["securityContext"]["runAsUser"] == 2000
