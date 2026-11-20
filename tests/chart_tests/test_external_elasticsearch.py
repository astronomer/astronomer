import base64
import json
import pathlib
import re

import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart

secret = base64.b64encode(b"sample-secret").decode()


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestExternalElasticSearch:
    # external-es-proxy templates gated purely by the logging.enabled helper.
    es_proxy_templates = [
        "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
        "charts/external-es-proxy/templates/external-es-proxy-env-configmap.yaml",
        "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
        "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
    ]

    def test_externalelasticsearch_with_secret(self, kube_version):
        """Test External ElasticSearch with secret passed from
        config/values.yaml."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True, "secret": secret}}},
            show_only=self.es_proxy_templates,
        )

        expected_nginx_mounts = [
            {"name": "tmp", "mountPath": "/tmp"},
            {
                "name": "tmp",
                "mountPath": "/usr/local/openresty/nginx/client_body_temp",
                "subPath": "openresty/nginx/client_body_temp",
            },
            {"name": "tmp", "mountPath": "/usr/local/openresty/nginx/proxy_temp", "subPath": "openresty/nginx/proxy_temp"},
            {"name": "tmp", "mountPath": "/usr/local/openresty/nginx/fastcgi_temp", "subPath": "openresty/nginx/fastcgi_temp"},
            {"name": "tmp", "mountPath": "/usr/local/openresty/nginx/uwsgi_temp", "subPath": "openresty/nginx/uwsgi_temp"},
            {"name": "tmp", "mountPath": "/usr/local/openresty/nginx/scgi_temp", "subPath": "openresty/nginx/scgi_temp"},
        ]
        assert len(docs) == 4
        deployment, _env_configmap, _configmap, service = docs
        assert deployment["kind"] == "Deployment"
        assert deployment["apiVersion"] == "apps/v1"
        assert deployment["metadata"]["name"] == "release-name-external-es-proxy"
        assert len(deployment["spec"]["template"]["spec"]["containers"]) == 1
        assert deployment["spec"]["template"]["spec"]["containers"][0]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 65534,
        }
        expected_env = [{"name": "ES_SECRET", "value": secret}]
        assert expected_env == deployment["spec"]["template"]["spec"]["containers"][0]["env"]
        container_mounts = deployment["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]
        assert {"name": "tmp", "mountPath": "/tmp"} in container_mounts
        for mount in expected_nginx_mounts:
            assert mount in container_mounts, f"Missing mount {mount}"
        volumes = deployment["spec"]["template"]["spec"]["volumes"]
        assert {"name": "tmp", "emptyDir": {}} in volumes

        assert service["kind"] == "Service"
        assert service["metadata"]["name"] == "release-name-external-es-proxy"
        assert service["spec"]["type"] == "ClusterIP"
        assert service["spec"]["ports"] == [
            {
                "name": "secure-http",
                "protocol": "TCP",
                "port": 9200,
                "appProtocol": "https",
            },
            {
                "name": "http",
                "protocol": "TCP",
                "port": 9201,
                "appProtocol": "http",
            },
        ]

    def test_externalelasticsearch_with_secretname(self, kube_version):
        """Test External ElasticSearch with secret passed as kubernetes
        secrets."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True, "secretName": "essecret"}}},
            show_only=self.es_proxy_templates,
        )

        assert len(docs) == 4
        deployment, _env_configmap, _configmap, service = docs
        assert deployment["kind"] == "Deployment"
        assert deployment["apiVersion"] == "apps/v1"
        assert deployment["metadata"]["name"] == "release-name-external-es-proxy"
        assert len(deployment["spec"]["template"]["spec"]["containers"]) == 1
        assert deployment["spec"]["template"]["spec"]["containers"][0]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 65534,
        }
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
        assert expected_env == deployment["spec"]["template"]["spec"]["containers"][0]["env"]

        assert service["kind"] == "Service"
        assert service["metadata"]["name"] == "release-name-external-es-proxy"
        assert service["spec"]["type"] == "ClusterIP"
        assert service["spec"]["ports"] == [
            {
                "name": "secure-http",
                "protocol": "TCP",
                "port": 9200,
                "appProtocol": "https",
            },
            {
                "name": "http",
                "protocol": "TCP",
                "port": 9201,
                "appProtocol": "http",
            },
        ]

    def test_externalelasticsearch_with_awsSecretName(self, kube_version):
        """Test External ElasticSearch with aws secret passed as kubernetes secret."""
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
        deployment, service, _configmap = docs
        assert deployment["kind"] == "Deployment"
        assert deployment["apiVersion"] == "apps/v1"
        assert deployment["metadata"]["name"] == "release-name-external-es-proxy"
        assert len(deployment["spec"]["template"]["spec"]["containers"]) == 2
        containers = get_containers_by_name(deployment)
        assert (
            {
                "allowPrivilegeEscalation": False,
                "capabilities": {"drop": ["ALL"]},
                "readOnlyRootFilesystem": True,
                "runAsNonRoot": True,
                "runAsUser": 65534,
            }
            == containers["awsproxy"]["securityContext"]
            == containers["external-es-proxy"]["securityContext"]
        )
        assert containers["awsproxy"]["env"] == [
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
        assert not containers["external-es-proxy"].get("env")

        assert service["kind"] == "Service"
        assert service["metadata"]["name"] == "release-name-external-es-proxy"
        assert service["spec"]["type"] == "ClusterIP"
        assert service["spec"]["ports"] == [
            {
                "name": "secure-http",
                "protocol": "TCP",
                "port": 9200,
                "appProtocol": "https",
            },
            {
                "name": "http",
                "protocol": "TCP",
                "port": 9201,
                "appProtocol": "http",
            },
        ]

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
        deployment, service = docs
        containers = get_containers_by_name(deployment)
        awsproxy_env_vars = get_env_vars_dict(containers["awsproxy"]["env"])
        assert awsproxy_env_vars["ENDPOINT"] == "https://esdemo.example.com"

        assert (
            deployment["spec"]["template"]["metadata"]["annotations"]["iam.amazonaws.com/role"]
            == "arn:aws:iam::xxxxxxxx:role/customrole"
        )
        assert len(deployment["spec"]["template"]["spec"]["containers"]) == 2
        containers = get_containers_by_name(deployment)
        assert (
            {
                "allowPrivilegeEscalation": False,
                "capabilities": {"drop": ["ALL"]},
                "readOnlyRootFilesystem": True,
                "runAsNonRoot": True,
                "runAsUser": 65534,
            }
            == containers["awsproxy"]["securityContext"]
            == containers["external-es-proxy"]["securityContext"]
        )

        assert service["kind"] == "Service"
        assert service["metadata"]["name"] == "release-name-external-es-proxy"
        assert service["spec"]["type"] == "ClusterIP"
        assert service["spec"]["ports"] == [
            {
                "name": "secure-http",
                "protocol": "TCP",
                "port": 9200,
                "appProtocol": "https",
            },
            {
                "name": "http",
                "protocol": "TCP",
                "port": 9201,
                "appProtocol": "http",
            },
        ]

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
        deployment, service_account, service = docs
        assert deployment["kind"] == "Deployment"
        assert len(deployment["spec"]["template"]["spec"]["containers"]) == 2
        containers = get_containers_by_name(deployment)
        assert (
            {
                "allowPrivilegeEscalation": False,
                "capabilities": {"drop": ["ALL"]},
                "readOnlyRootFilesystem": True,
                "runAsNonRoot": True,
                "runAsUser": 65534,
            }
            == containers["awsproxy"]["securityContext"]
            == containers["external-es-proxy"]["securityContext"]
        )
        awsproxy_env_vars = get_env_vars_dict(containers["awsproxy"]["env"])
        assert awsproxy_env_vars["ENDPOINT"] == "https://esdemo.example.com"

        assert service_account["metadata"]["annotations"]["eks.amazonaws.com/role-arn"] == "arn:aws:iam::xxxxxxxx:role/customrole"

        assert service["kind"] == "Service"
        assert service["metadata"]["name"] == "release-name-external-es-proxy"
        assert service["spec"]["type"] == "ClusterIP"
        assert service["spec"]["ports"] == [
            {
                "name": "secure-http",
                "protocol": "TCP",
                "port": 9200,
                "appProtocol": "https",
            },
            {
                "name": "http",
                "protocol": "TCP",
                "port": 9201,
                "appProtocol": "http",
            },
        ]

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
        networkpolicy = docs[0]
        assert networkpolicy["kind"] == "NetworkPolicy"
        assert [
            {
                "namespaceSelector": {},
                "podSelector": {"matchLabels": {"tier": "airflow", "component": "webserver"}},
            },
            {
                "namespaceSelector": {},
                "podSelector": {"matchLabels": {"tier": "airflow", "component": "api-server"}},
            },
            {"podSelector": {"matchLabels": {"component": "houston", "tier": "astronomer", "release": "release-name"}}},
            {"podSelector": {"matchLabels": {"component": "houston-worker", "tier": "astronomer", "release": "release-name"}}},
        ] == networkpolicy["spec"]["ingress"][0]["from"]

    def test_external_es_network_selector_plane_mode_data(self, kube_version):
        """Test External Elasticsearch Service with NetworkPolicies."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
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
        networkpolicy = docs[0]
        assert networkpolicy["kind"] == "NetworkPolicy"
        assert networkpolicy["spec"]["ingress"] == [
            {
                "from": [
                    {"namespaceSelector": {}, "podSelector": {"matchLabels": {"component": "webserver", "tier": "airflow"}}},
                    {"namespaceSelector": {}, "podSelector": {"matchLabels": {"component": "api-server", "tier": "airflow"}}},
                    {
                        "podSelector": {
                            "matchLabels": {"component": "dp-ingress-controller", "release": "release-name", "tier": "nginx"}
                        }
                    },
                    {"podSelector": {"matchLabels": {"component": "houston", "release": "release-name", "tier": "astronomer"}}},
                    {
                        "podSelector": {
                            "matchLabels": {"component": "houston-worker", "release": "release-name", "tier": "astronomer"}
                        }
                    },
                ],
                "ports": [{"port": 9200, "protocol": "TCP"}],
            },
            {
                "from": [
                    {"podSelector": {"matchLabels": {"component": "vector", "release": "release-name", "tier": "logging"}}},
                ],
                "ports": [{"port": 9201, "protocol": "TCP"}],
            },
        ]

    def test_external_es_network_selector_with_auth_sidecar_enabled(self, kube_version):
        """Test External Elasticsearch Service with authSidecar enabled."""
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
                    "authSidecar": {"enabled": True},
                    "networkPolicy": {"enabled": True},
                    "plane": {"mode": "data"},
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1
        networkpolicy = docs[0]
        assert networkpolicy["kind"] == "NetworkPolicy"
        assert [
            ingress_rule_item
            for rule in networkpolicy["spec"]["ingress"]
            for ingress_rule_item in rule.get("from")
            if ingress_rule_item.get("namespaceSelector")
        ] == [{"namespaceSelector": {"matchLabels": {"network.openshift.io/policy-group": "ingress"}}}]

    def test_external_es_network_selector_with_auth_sidecar_enabled_with_ingress_allowed_namespaces(self, kube_version):
        """Test External Elasticsearch Service with authSidecar enabled."""
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
                    "authSidecar": {
                        "enabled": True,
                        "ingressAllowedNamespaces": [
                            "test-namespace-1",
                            "test-namespace-2",
                        ],
                    },
                    "networkPolicy": {"enabled": True},
                    "plane": {"mode": "data"},
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1
        networkpolicy = docs[0]
        assert networkpolicy["kind"] == "NetworkPolicy"
        assert [
            ingress_rule_item
            for rule in networkpolicy["spec"]["ingress"]
            for ingress_rule_item in rule.get("from")
            if ingress_rule_item.get("namespaceSelector")
        ] == [
            {"namespaceSelector": {"matchLabels": {"network.openshift.io/policy-group": "ingress"}}},
            {
                "namespaceSelector": {
                    "matchExpressions": [
                        {"key": "kubernetes.io/metadata.name", "operator": "In", "values": ["test-namespace-1", "test-namespace-2"]}
                    ]
                }
            },
        ]

    def test_external_es_network_selector_with_logging_sidecar_enabled(self, kube_version):
        """Test External Elasticsearch Service with loggingSidecar enabled."""
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
                    "logging": {"loggingSidecar": {"enabled": True}},
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1
        networkpolicy = docs[0]
        assert networkpolicy["kind"] == "NetworkPolicy"
        assert not [
            ingress_rule_item
            for rule in networkpolicy["spec"]["ingress"]
            for ingress_rule_item in rule.get("from")
            if ingress_rule_item.get("namespaceSelector")
        ]
        assert [
            {"namespaceSelector": {}, "podSelector": {"matchLabels": {"tier": "airflow", "component": "webserver"}}},
            {"namespaceSelector": {}, "podSelector": {"matchLabels": {"tier": "airflow", "component": "api-server"}}},
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
            {"podSelector": {"matchLabels": {"component": "houston", "tier": "astronomer", "release": "release-name"}}},
            {"podSelector": {"matchLabels": {"component": "houston-worker", "tier": "astronomer", "release": "release-name"}}},
        ] == networkpolicy["spec"]["ingress"][0]["from"]

    def test_external_es_index_pattern_defaults(self, kube_version):
        """Test External Elasticsearch Service Index Pattern Search defaults."""
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
        configmap = docs[0]
        es_index = configmap["data"]["nginx.conf"]
        assert configmap["kind"] == "ConfigMap"
        assert "fluentd.$es_scope.*" in es_index

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
        assert "astronomer.$es_scope.*" in es_index

    def test_external_es_index_pattern_sidecar_logging_overrides(self, kube_version):
        """Test External Elasticsearch Service Index Pattern Search
        overrides."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "logging": {"indexNamePrefix": "astronomer", "loggingSidecar": {"enabled": True}},
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
        assert "astronomer.$es_scope.*" in es_index

    def test_external_es_index_pattern_sidecar_logging_defaults(self, kube_version):
        """Test External Elasticsearch Service Index Pattern Search
        overrides."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "logging": {"loggingSidecar": {"enabled": True}},
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
        assert "vector.$es_scope.*" in es_index

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
                    "logging": {"loggingSidecar": {"enabled": True}},
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
        assert "vector.$es_scope.*" in es_index

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
                "charts/elasticsearch/templates/es-ingress.yaml",
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

    def test_external_elasticsearch_ingress_plane_mode_data(self, kube_version):
        """Test that External ElasticSearch Ingress is rendered when global.plane.mode is 'data'."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data", "domainPrefix": "plane"},
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
        assert doc["spec"]["rules"][0]["host"] == "elasticsearch.plane.example.com"

    def test_external_es_proxy_auth_cache_enabled_by_default(self, kube_version):
        """Test that auth caching is enabled by default in external-es-proxy configmap."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True, "secret": secret}}},
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"

        nginx_config = doc["data"]["nginx.conf"]

        # Verify cache path is configured
        assert "proxy_cache_path /tmp/nginx-auth-cache" in nginx_config
        assert "levels=1:2" in nginx_config
        assert "keys_zone=auth_cache:10m" in nginx_config
        assert "max_size=100m" in nginx_config
        assert "inactive=5m" in nginx_config

        # Verify cache directives in /auth location
        assert "proxy_cache auth_cache" in nginx_config
        assert 'proxy_cache_key "$http_authorization|$http_cookie|$request_uri"' in nginx_config
        assert "proxy_cache_valid 200 5m" in nginx_config
        assert "proxy_cache_valid 401 403 1m" in nginx_config
        assert "proxy_ignore_headers Cache-Control Expires" in nginx_config
        assert "add_header X-Auth-Cache-Status $upstream_cache_status always" in nginx_config

        # Verify proxy_pass_request_body optimization is present
        assert "proxy_pass_request_body off" in nginx_config

    def test_external_es_proxy_auth_cache_disabled(self, kube_version):
        """Test that auth caching can be disabled in external-es-proxy configmap."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"customLogging": {"enabled": True, "secret": secret}},
                "external-es-proxy": {"authCache": {"enabled": False}},
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"

        nginx_config = doc["data"]["nginx.conf"]

        # Verify cache directives are NOT present when disabled
        assert "proxy_cache_path" not in nginx_config
        assert "proxy_cache auth_cache" not in nginx_config
        assert "proxy_cache_key" not in nginx_config
        assert "proxy_cache_valid" not in nginx_config
        assert "X-Auth-Cache-Status" not in nginx_config

    def test_external_es_proxy_auth_cache_custom_settings(self, kube_version):
        """Test that custom auth cache settings are properly rendered."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"customLogging": {"enabled": True, "secret": secret}},
                "external-es-proxy": {
                    "authCache": {
                        "enabled": True,
                        "levels": "2:2",
                        "keysZone": "custom_cache:20m",
                        "maxSize": "200m",
                        "inactive": "10m",
                        "validSuccess": "10m",
                        "validFailure": "2m",
                    }
                },
            },
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"

        nginx_config = doc["data"]["nginx.conf"]

        # Verify custom cache storage settings (path is always /tmp/nginx-auth-cache)
        assert "proxy_cache_path /tmp/nginx-auth-cache" in nginx_config
        assert "levels=2:2" in nginx_config
        assert "keys_zone=custom_cache:20m" in nginx_config
        assert "max_size=200m" in nginx_config
        assert "inactive=10m" in nginx_config

        # Verify custom TTL settings
        assert "proxy_cache_valid 200 10m" in nginx_config
        assert "proxy_cache_valid 401 403 2m" in nginx_config

    def test_external_elasticsearch_ingress_with_tls_secret(self, kube_version):
        """Test that external-es-proxy ingress includes tls with hosts when tlsSecret is set."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/external-es-proxy/templates/external-es-proxy-ingress.yaml"],
            values={
                "global": {
                    "baseDomain": "example.com",
                    "tlsSecret": "my-tls-secret",
                    "customLogging": {"enabled": True},
                    "plane": {"mode": "data"},
                },
            },
        )

        assert len(docs) == 1
        tls = docs[0]["spec"]["tls"]
        assert len(tls) == 1
        assert tls[0]["secretName"] == "my-tls-secret"
        assert "hosts" in tls[0]
        assert len(tls[0]["hosts"]) == 1

    def test_external_elasticsearch_ingress_without_tls_secret(self, kube_version):
        """Test that external-es-proxy ingress does not include tls when tlsSecret is empty."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/external-es-proxy/templates/external-es-proxy-ingress.yaml"],
            values={
                "global": {
                    "baseDomain": "example.com",
                    "tlsSecret": "",
                    "customLogging": {"enabled": True},
                    "plane": {"mode": "data"},
                },
            },
        )

        assert len(docs) == 1
        assert "tls" not in docs[0]["spec"]

    @pytest.mark.parametrize(
        "mode,shared_elasticsearch,should_render",
        [
            # unified: logging is always enabled regardless of sharedElasticsearch
            ("unified", False, True),
            ("unified", True, True),
            # control: logging is enabled only when sharedElasticsearch is enabled
            ("control", False, False),
            ("control", True, True),
            # data: logging is enabled only when sharedElasticsearch is disabled
            ("data", False, True),
            ("data", True, False),
        ],
    )
    def test_external_es_proxy_logging_enabled_by_mode_and_shared_elasticsearch(
        self, kube_version, mode, shared_elasticsearch, should_render
    ):
        """Test that external-es-proxy renders according to the logging.enabled helper across plane mode and sharedElasticsearch."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.es_proxy_templates,
            values={
                "global": {
                    "customLogging": {"enabled": True},
                    "plane": {"mode": mode},
                    "sharedElasticsearch": {"enabled": shared_elasticsearch},
                },
            },
        )

        if should_render:
            assert len(docs) == len(self.es_proxy_templates)
            assert all(doc.get("apiVersion") for doc in docs)
            assert all(doc.get("kind") for doc in docs)
        else:
            assert len(docs) == 0


ES_PROXY_CONFIGMAP = "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml"
ES_PROXY_NETWORK_POLICY = "charts/external-es-proxy/templates/external-es-proxy-networkpolicy.yaml"
ES_PROXY_INGRESS = "charts/external-es-proxy/templates/external-es-proxy-ingress.yaml"


def _server_blocks(nginx_conf: str) -> dict[int, str]:
    """The text of each ``server { ... }`` block in an nginx.conf, keyed by the port it listens on."""
    blocks = {}
    for match in re.finditer(r"^  server \{\n(.*?)^  \}\n", nginx_conf, re.DOTALL | re.MULTILINE):
        body = match.group(1)
        blocks[int(re.search(r"listen (\d+);", body).group(1))] = body
    return blocks


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestExternalEsProxyAuthorization:
    """APC-2206: the authenticated port (9200) is the one reachable from outside and must scope every request to the
    deployment Houston names; the in-cluster port (9201) stays open for the Vector DaemonSet and must stay private."""

    custom_logging = {"enabled": True, "scheme": "https", "host": "esdemo.example.com", "port": 9243, "secret": secret}

    def _nginx_conf(self, kube_version, custom_logging=None, extra_global=None):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": custom_logging or self.custom_logging, **(extra_global or {})}},
            show_only=[ES_PROXY_CONFIGMAP],
        )
        return docs[0]["data"]["nginx.conf"]

    def test_authenticated_port_asks_houston_v2(self, kube_version):
        """The 9200 server authorizes through /v2/elasticsearch, not the deployment-credentials-only /v1."""
        auth_server = _server_blocks(self._nginx_conf(kube_version))[9200]
        assert "/v2/elasticsearch;" in auth_server
        assert "/v1/elasticsearch" not in auth_server

    def test_authenticated_port_sends_the_real_path_to_houston(self, kube_version):
        """Houston decides per path, and the control plane's ingress controller overwrites X-Original-URI."""
        auth_server = _server_blocks(self._nginx_conf(kube_version))[9200]
        assert "proxy_set_header X-ES-Original-URI $request_uri;" in auth_server

    @pytest.mark.parametrize("operation", ["_search", "_count", "_bulk"])
    def test_authenticated_port_builds_the_index_from_houstons_scope(self, kube_version, operation):
        """The index comes from Houston's answer, never from the URL or the caller's own user name."""
        auth_server = _server_blocks(self._nginx_conf(kube_version))[9200]
        assert "auth_request_set $es_scope $upstream_http_x_elasticsearch_index_scope;" in auth_server
        assert f"proxy_pass https://external_es/fluentd.$es_scope.*/{operation}$is_args$args;" in auth_server

    def test_authenticated_port_no_longer_scopes_by_remote_user(self, kube_version):
        """$remote_user is whatever the caller typed; a Houston user or bot has none that names a deployment."""
        assert "$remote_user" not in _server_blocks(self._nginx_conf(kube_version))[9200]

    def test_authenticated_port_refuses_everything_else(self, kube_version):
        """Anything but search, count, bulk and the two cluster reads is denied, as on the ES nginx proxy."""
        auth_server = _server_blocks(self._nginx_conf(kube_version))[9200]
        assert re.search(r"location ~ \^/ \{\s+deny all;\s+\}", auth_server)

    def test_authenticated_port_forwards_to_the_customer_host_through_an_upstream(self, kube_version):
        """proxy_pass with a variable URI needs an upstream group, and the Host and TLS name must stay the customer's."""
        nginx_conf = self._nginx_conf(kube_version)
        auth_server = _server_blocks(nginx_conf)[9200]
        assert "upstream external_es {\n    server esdemo.example.com:9243;\n  }" in nginx_conf
        assert "proxy_set_header Host esdemo.example.com:9243;" in auth_server
        assert "proxy_ssl_name esdemo.example.com;" in auth_server

    def test_authenticated_port_still_injects_the_stored_credential(self, kube_version):
        """The customer's ES login is added after Houston has said yes, as before."""
        auth_server = _server_blocks(self._nginx_conf(kube_version))[9200]
        assert "access_by_lua_file /usr/local/openresty/nginx/conf/setenv.lua;" in auth_server

    def test_authenticated_port_through_the_aws_signing_proxy(self, kube_version):
        """With the AWS signing proxy the scoped requests go to it, and the Lua credential is not added."""
        custom_logging = {"enabled": True, "host": "esdemo.example.com", "awsSecretName": "awssecret"}
        nginx_conf = self._nginx_conf(kube_version, custom_logging)
        auth_server = _server_blocks(nginx_conf)[9200]
        assert "upstream external_es {\n    server localhost:9203;\n  }" in nginx_conf
        assert "proxy_pass http://external_es/fluentd.$es_scope.*/_search$is_args$args;" in auth_server
        assert "setenv.lua" not in auth_server

    @pytest.mark.parametrize(
        "aws_option",
        [
            {"awsSecretName": "awssecret"},
            {"awsServiceAccountAnnotation": "arn:aws:iam::123456789012:role/customrole"},
            {"awsIAMRole": "arn:aws:iam::123456789012:role/customrole"},
        ],
        ids=["static-keys-secret", "irsa", "kube2iam"],
    )
    def test_every_aws_option_switches_the_sidecar_and_the_forwarding_together(self, kube_version, aws_option):
        """The sidecar container, the upstream and the scoped locations share one "uses AWS" decision, so any of the
        three AWS options turns all of them on and none can be left pointing at the wrong place."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True, "host": "esdemo.example.com", **aws_option}}},
            show_only=[ES_PROXY_CONFIGMAP, "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml"],
        )
        configmap, deployment = docs
        nginx_conf = configmap["data"]["nginx.conf"]
        containers = [c["name"] for c in deployment["spec"]["template"]["spec"]["containers"]]
        assert "awsproxy" in containers
        assert "upstream external_es {\n    server localhost:9203;\n  }" in nginx_conf
        assert "proxy_pass http://external_es/fluentd.$es_scope.*/_search$is_args$args;" in nginx_conf

    def test_without_an_aws_option_nothing_routes_through_the_signing_proxy(self, kube_version):
        """The mirror image: with no AWS option there is no sidecar and the upstream is the customer's own host."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True, "host": "esdemo.example.com", "port": 9243, "secret": secret}}},
            show_only=[ES_PROXY_CONFIGMAP, "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml"],
        )
        configmap, deployment = docs
        containers = [c["name"] for c in deployment["spec"]["template"]["spec"]["containers"]]
        assert "awsproxy" not in containers
        assert "server esdemo.example.com:9243;" in configmap["data"]["nginx.conf"]
        assert "localhost:9203" not in configmap["data"]["nginx.conf"]

    def test_auth_cache_is_keyed_on_the_whole_request(self, kube_version):
        """Houston's answer depends on credential, cookie and path, so the cache key carries all three."""
        auth_server = _server_blocks(self._nginx_conf(kube_version))[9200]
        assert 'proxy_cache_key "$http_authorization|$http_cookie|$request_uri";' in auth_server

    def test_auth_cache_skips_requests_without_a_credential(self, kube_version):
        """A request with neither header has nothing to key an answer on, so it must never be cached."""
        nginx_conf = self._nginx_conf(kube_version)
        auth_server = _server_blocks(nginx_conf)[9200]
        assert 'map "$http_authorization$http_cookie" $es_auth_uncacheable' in nginx_conf
        assert "proxy_cache_bypass $es_auth_uncacheable;" in auth_server
        assert "proxy_no_cache $es_auth_uncacheable;" in auth_server

    def test_in_cluster_port_stays_open_for_vector(self, kube_version):
        """The Vector DaemonSet has no credentials, so 9201 injects the stored one without asking Houston."""
        in_cluster = _server_blocks(self._nginx_conf(kube_version))[9201]
        assert "auth_request" not in in_cluster
        assert "access_by_lua_file" in in_cluster
        assert "proxy_pass https://esdemo.example.com:9243;" in in_cluster

    def test_ingress_targets_the_authenticated_port(self, kube_version):
        """The public host must reach the port that asks Houston, never the open in-cluster one."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}, "customLogging": self.custom_logging}},
            show_only=[ES_PROXY_INGRESS],
        )
        assert docs[0]["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["port"]["number"] == 9200

    @pytest.mark.parametrize("auth_sidecar", [False, True], ids=["ingress-controller", "auth-sidecar"])
    def test_ingress_peers_can_reach_only_the_authenticated_port(self, kube_version, auth_sidecar):
        """The ingress controller is allowed on 9200 only, so the open 9201 port is unreachable from outside."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                    "customLogging": self.custom_logging,
                    "authSidecar": {"enabled": auth_sidecar},
                    "networkPolicy": {"enabled": True},
                },
            },
            show_only=[ES_PROXY_NETWORK_POLICY],
        )
        by_port = {rule["ports"][0]["port"]: json.dumps(rule["from"]) for rule in docs[0]["spec"]["ingress"]}
        peer = "policy-group" if auth_sidecar else "dp-ingress-controller"
        assert peer in by_port[9200]
        assert peer not in by_port[9201]
        assert "vector" in by_port[9201]

    def test_in_cluster_port_admits_only_vector(self, kube_version):
        """Houston authenticates with its read token on 9200, so the unauthenticated 9201 is for Vector alone."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": self.custom_logging, "networkPolicy": {"enabled": True}}},
            show_only=[ES_PROXY_NETWORK_POLICY],
        )
        rules = {rule["ports"][0]["port"]: json.dumps(rule["from"]) for rule in docs[0]["spec"]["ingress"]}
        assert "houston" not in rules[9201]
        assert "houston" in rules[9200]
        assert "houston-worker" in rules[9200]


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestHoustonReadsLogsThroughTheAuthenticatedPort:
    """APC-2206: Commander relays COMMANDER_ELASTICSEARCH_NODE to Houston, which stores it and reads logs from it.
    On a unified install with customLogging that must be the authenticated port, never the Vector-only one."""

    houston_configmap = "charts/astronomer/templates/houston/houston-configmap.yaml"
    commander_deployment = "charts/astronomer/templates/commander/commander-deployment.yaml"

    def test_houston_default_elasticsearch_node_is_the_authenticated_port(self, kube_version):
        """The configmap value is Houston's fallback when a cluster has no stored node; it must not be port 9201."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True, "secret": secret, "host": "esdemo.example.com"}}},
            show_only=[self.houston_configmap],
        )
        config = yaml.safe_load(docs[0]["data"]["production.yaml"])
        assert config["elasticsearch"]["client"]["node"] == "http://release-name-external-es-proxy:9200"

    def test_airflow_connection_stays_on_the_authenticated_port(self, kube_version):
        """What deployments get (Airflow, the sidecar) is the authenticated port, unchanged."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True, "secret": secret, "host": "esdemo.example.com"}}},
            show_only=[self.houston_configmap],
        )
        config = yaml.safe_load(docs[0]["data"]["production.yaml"])
        connection = config["deployments"]["helm"]["airflow"]["elasticsearch"]["connection"]
        assert connection["port"] == 9200
