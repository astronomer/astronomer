import base64
import pathlib

import jmespath
import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart

secret = base64.b64encode(b"sample-secret").decode()


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestExternalElasticSearch:
    def test_externalelasticsearch_with_secret(self, kube_version):
        """Test External ElasticSearch with secret passed from
        config/values.yaml."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True, "secret": secret}}},
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-env-configmap.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
            ],
        )

        assert len(docs) == 4
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-external-es-proxy"
        expected_env = [{"name": "ES_SECRET", "value": secret}]
        assert expected_env == doc["spec"]["template"]["spec"]["containers"][0]["env"]

        assert "Service" == jmespath.search("kind", docs[3])
        assert "release-name-external-es-proxy" == jmespath.search("metadata.name", docs[3])
        assert "ClusterIP" == jmespath.search("spec.type", docs[3])
        assert {
            "name": "secure-http",
            "protocol": "TCP",
            "port": 9200,
            "appProtocol": "https",
        } in jmespath.search("spec.ports", docs[3])
        assert {
            "name": "http",
            "protocol": "TCP",
            "port": 9201,
            "appProtocol": "http",
        } in jmespath.search("spec.ports", docs[3])

    def test_externalelasticsearch_with_secretname(self, kube_version):
        """Test External ElasticSearch with secret passed as kubernetes
        secrets."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True, "secretName": "essecret"}}},
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-env-configmap.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
            ],
        )

        assert len(docs) == 4
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-external-es-proxy"
        expected_env = [
            {
                "name": "ES_SECRET_NAME",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "essecret",
                        "key": "elastic",
                    },
                },
            }
        ]
        assert expected_env == doc["spec"]["template"]["spec"]["containers"][0]["env"]

        assert "Service" == jmespath.search("kind", docs[3])
        assert "release-name-external-es-proxy" == jmespath.search("metadata.name", docs[3])
        assert "ClusterIP" == jmespath.search("spec.type", docs[3])
        assert {
            "name": "secure-http",
            "protocol": "TCP",
            "port": 9200,
            "appProtocol": "https",
        } in jmespath.search("spec.ports", docs[3])
        assert {
            "name": "http",
            "protocol": "TCP",
            "port": 9201,
            "appProtocol": "http",
        } in jmespath.search("spec.ports", docs[3])

    def test_externalelasticsearch_with_awsSecretName(self, kube_version):
        """Test External ElasticSearch with aws secret passed as kubernetes
        secret."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsSecretName": "awssecret",
                    }
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
            ],
        )

        assert len(docs) == 3
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-external-es-proxy"
        expected_env = [
            {
                "name": "AWS_ACCESS_KEY_ID",
                "valueFrom": {"secretKeyRef": {"name": "awssecret", "key": "aws_access_key"}},
            },
            {
                "name": "AWS_SECRET_ACCESS_KEY",
                "valueFrom": {"secretKeyRef": {"name": "awssecret", "key": "aws_secret_key"}},
            },
            {"name": "ENDPOINT", "value": "https://esdemo.example.com"},
        ]
        assert expected_env == doc["spec"]["template"]["spec"]["containers"][1]["env"]

        assert "Service" == jmespath.search("kind", docs[1])
        assert "release-name-external-es-proxy" == jmespath.search("metadata.name", docs[1])
        assert "ClusterIP" == jmespath.search("spec.type", docs[1])
        assert {
            "name": "secure-http",
            "protocol": "TCP",
            "port": 9200,
            "appProtocol": "https",
        } in jmespath.search("spec.ports", docs[1])
        assert {
            "name": "http",
            "protocol": "TCP",
            "port": 9201,
            "appProtocol": "http",
        } in jmespath.search("spec.ports", docs[1])

        nginx_conf = pathlib.Path("tests/chart_tests/test_data/external-es-nginx-with-aws-secrets.conf").read_text()
        assert nginx_conf in docs[2]["data"]["nginx.conf"]

    def test_externalelasticsearch_with_awsIAMRole(self, kube_version):
        """Test External ElasticSearch with iam roles passed as Deployment
        annotation."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsIAMRole": "arn:aws:iam::xxxxxxxx:role/customrole",
                    }
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
            ],
        )

        assert len(docs) == 2
        doc = docs[0]
        expected_env = [{"name": "ENDPOINT", "value": "https://esdemo.example.com"}]

        assert expected_env == doc["spec"]["template"]["spec"]["containers"][1]["env"]

        assert "arn:aws:iam::xxxxxxxx:role/customrole" == jmespath.search(
            'spec.template.metadata.annotations."iam.amazonaws.com/role"', docs[0]
        )

        assert "Service" == jmespath.search("kind", docs[1])
        assert "release-name-external-es-proxy" == jmespath.search("metadata.name", docs[1])
        assert "ClusterIP" == jmespath.search("spec.type", docs[1])
        assert {
            "name": "secure-http",
            "protocol": "TCP",
            "port": 9200,
            "appProtocol": "https",
        } in jmespath.search("spec.ports", docs[1])
        assert {
            "name": "http",
            "protocol": "TCP",
            "port": 9201,
            "appProtocol": "http",
        } in jmespath.search("spec.ports", docs[1])

    def test_externalelasticsearch_with_awsServiceAccountAnnotation(self, kube_version):
        """Test External ElasticSearch with eks iam roles passed as Service
        Account Annotation."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsServiceAccountAnnotation": "arn:aws:iam::xxxxxxxx:role/customrole",
                    }
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-serviceaccount.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
            ],
        )

        assert len(docs) == 3
        doc = docs[0]
        expected_env = [{"name": "ENDPOINT", "value": "https://esdemo.example.com"}]

        assert expected_env == doc["spec"]["template"]["spec"]["containers"][1]["env"]

        doc = docs[1]

        assert "arn:aws:iam::xxxxxxxx:role/customrole" == jmespath.search('metadata.annotations."eks.amazonaws.com/role-arn"', doc)

        assert "Service" == jmespath.search("kind", docs[2])
        assert "release-name-external-es-proxy" == jmespath.search("metadata.name", docs[2])
        assert "ClusterIP" == jmespath.search("spec.type", docs[2])
        assert {
            "name": "secure-http",
            "protocol": "TCP",
            "port": 9200,
            "appProtocol": "https",
        } in jmespath.search("spec.ports", docs[2])
        assert {
            "name": "http",
            "protocol": "TCP",
            "port": 9201,
            "appProtocol": "http",
        } in jmespath.search("spec.ports", docs[2])

    def test_external_es_network_selector_defaults(self, kube_version):
        """Test External Elasticsearch Service with NetworkPolicies."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsServiceAccountAnnotation": "arn:aws:iam::xxxxxxxx:role/customrole",
                    },
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "NetworkPolicy"
        assert [
            {
                "namespaceSelector": {},
                "podSelector": {"matchLabels": {"tier": "airflow", "component": "webserver"}},
            },
        ] == doc["spec"]["ingress"][0]["from"]

    def test_external_es_network_selector_with_logging_sidecar_enabled(self, kube_version):
        """Test External Elasticsearch Service with NetworkPolicy Defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsServiceAccountAnnotation": "arn:aws:iam::xxxxxxxx:role/customrole",
                    },
                    "loggingSidecar": {"enabled": True},
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "NetworkPolicy"
        assert [
            {"namespaceSelector": {}, "podSelector": {"matchLabels": {"tier": "airflow", "component": "webserver"}}},
            {
                "namespaceSelector": {},
                "podSelector": {
                    "matchExpressions": [
                        {
                            "key": "component",
                            "operator": "In",
                            "values": [
                                "dag-server",
                                "metacleanup",
                                "airflow-downgrade",
                                "git-sync-relay",
                                "dag-processor",
                                "triggerer",
                                "worker",
                                "scheduler",
                            ],
                        }
                    ],
                    "matchLabels": {"tier": "airflow"},
                },
            },
        ] == doc["spec"]["ingress"][0]["from"]

    def test_external_es_index_pattern_defaults(self, kube_version):
        """Test External Elasticsearch Service Index Pattern Search
        defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsServiceAccountAnnotation": "arn:aws:iam::xxxxxxxx:role/customrole",
                    },
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        es_index = doc["data"]["nginx.conf"]
        assert doc["kind"] == "ConfigMap"
        assert "fluentd.$remote_user.*" in es_index

    def test_external_es_index_pattern_overrides(self, kube_version):
        """Test External Elasticsearch Service Index Pattern Search
        overrides."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "logging": {"indexNamePrefix": "astronomer"},
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsServiceAccountAnnotation": "arn:aws:iam::xxxxxxxx:role/customrole",
                    },
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        es_index = doc["data"]["nginx.conf"]
        assert doc["kind"] == "ConfigMap"
        assert "astronomer.$remote_user.*" in es_index

    def test_external_es_index_pattern_sidecar_logging_overrides(self, kube_version):
        """Test External Elasticsearch Service Index Pattern Search
        overrides."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "logging": {"indexNamePrefix": "astronomer"},
                    "loggingSidecar": {"enabled": True},
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsServiceAccountAnnotation": "arn:aws:iam::xxxxxxxx:role/customrole",
                    },
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        es_index = doc["data"]["nginx.conf"]
        assert doc["kind"] == "ConfigMap"
        assert "astronomer.$remote_user.*" in es_index

    def test_external_es_index_pattern_sidecar_logging_defaults(self, kube_version):
        """Test External Elasticsearch Service Index Pattern Search
        overrides."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "loggingSidecar": {"enabled": True},
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsServiceAccountAnnotation": "arn:aws:iam::xxxxxxxx:role/customrole",
                    },
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        es_index = doc["data"]["nginx.conf"]
        assert doc["kind"] == "ConfigMap"
        assert "fluentd.$remote_user.*" in es_index

    def test_external_es_index_pattern_with_sidecar_logging_enabled(self, kube_version):
        """Test External Elasticsearch Service Index Pattern Search with
        sidecar logging."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsServiceAccountAnnotation": "arn:aws:iam::xxxxxxxx:role/customrole",
                    },
                    "loggingSidecar": {"enabled": True},
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        es_index = doc["data"]["nginx.conf"]
        assert doc["kind"] == "ConfigMap"
        assert "fluentd.$remote_user.*" in es_index

    def test_external_es_with_private_registry_enabled(self, kube_version):
        """Test External Elasticsearch Service with Private Registry
        Enabled."""
        private_registry = "private-registry.example.com"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        "repository": private_registry,
                    },
                    "customLogging": {
                        "enabled": True,
                        "scheme": "https",
                        "host": "esdemo.example.com",
                        "awsServiceAccountAnnotation": "arn:aws:iam::xxxxxxxx:role/customrole",
                    },
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=False)

        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        for name, container in c_by_name.items():
            assert container["image"].startswith(private_registry), (
                f"Container named '{name}' does not use registry '{private_registry}': {container}"
            )

    def test_externalelasticsearch_with_extraenv(self, kube_version):
        """Test External ElasticSearch with custom env passed from
        config/values.yaml."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "secret": secret,
                        "extraEnv": [
                            {"name": "TEST_VAR_NAME", "value": "test_var_value"},
                        ],
                    }
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-external-es-proxy"
        assert {"name": "TEST_VAR_NAME", "value": "test_var_value"} in doc["spec"]["template"]["spec"]["containers"][0]["env"]

    def test_external_elasticsearch_nginx_defaults_config(self, kube_version):
        """Test External ElasticSearch with nginx defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "secret": secret,
                        "host": "esdemo.example.com",
                    }
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        nginx_conf = pathlib.Path("tests/chart_tests/test_data/default-external-es-nginx.conf").read_text()
        assert doc["kind"] == "ConfigMap"
        assert nginx_conf in doc["data"]["nginx.conf"]

    def test_external_elasticsearch_nginx_deployment_defaults(self, kube_version):
        """Test that External ElasticSearch renders proper nodeSelector, affinity,
        and tolerations with global and nginx defaults"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "customLogging": {
                        "enabled": True,
                        "secret": secret,
                        "host": "esdemo.example.com",
                    }
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
            ],
        )

        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert spec["nodeSelector"] == {}
        assert spec["affinity"] == {}
        assert spec["tolerations"] == []

    def test_external_elasticsearch_nginx_deployment_global_platformnodepool_overrides(
        self, kube_version, global_platform_node_pool_config
    ):
        """Test that External ElasticSearch renders proper nodeSelector, affinity,
        and tolerations with global config and nginx overrides."""
        values = {
            "global": {
                "platformNodePool": global_platform_node_pool_config,
                "customLogging": {
                    "enabled": True,
                    "secret": secret,
                    "host": "esdemo.example.com",
                },
            }
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
            ],
        )

        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert len(spec["nodeSelector"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["global"]["platformNodePool"]["tolerations"]

    def test_external_elasticsearch_nginx_deployment_with_subchart_overrides(self, kube_version, global_platform_node_pool_config):
        """Test that External ElasticSearch renders proper nodeSelector, affinity,
        and tolerations with global config and nginx overrides."""
        global_platform_node_pool_config["nodeSelector"] = {"role": "astroesproxy"}
        values = {
            "global": {
                "customLogging": {
                    "enabled": True,
                    "secret": secret,
                    "host": "esdemo.example.com",
                },
            },
            "external-es-proxy": global_platform_node_pool_config,
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
            ],
        )

        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert len(spec["nodeSelector"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["external-es-proxy"]["tolerations"]

    def test_external_elasticsearch_ingress(self, kube_version):
        """Test that External ElasticSearch Ingress is rendered when
        global.plane.mode is 'data'."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data", "domainSuffix": "plane"},
                    "baseDomain": "example.com",
                    "customLogging": {
                        "enabled": True,
                        "secret": secret,
                        "host": "esdemo.example.com",
                    },
                }
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-ingress.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Ingress"
        assert doc["metadata"]["name"] == "release-name-external-es-proxy-ingress"
        assert doc["spec"]["rules"][0]["host"] == "es-proxy.plane.example.com"
