import base64
import pathlib

import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
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
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
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
            show_only=[
                "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-env-configmap.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
                "charts/external-es-proxy/templates/external-es-proxy-service.yaml",
            ],
        )

        assert len(docs) == 4
        deployment, _env_configmap, _configmap, service = docs
        assert deployment["kind"] == "Deployment"
        assert deployment["apiVersion"] == "apps/v1"
        assert deployment["metadata"]["name"] == "release-name-external-es-proxy"
        assert len(deployment["spec"]["template"]["spec"]["containers"]) == 1
        assert deployment["spec"]["template"]["spec"]["containers"][0]["securityContext"] == {
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
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
                "readOnlyRootFilesystem": True,
                "runAsNonRoot": True,
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
                "readOnlyRootFilesystem": True,
                "runAsNonRoot": True,
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
                "readOnlyRootFilesystem": True,
                "runAsNonRoot": True,
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
        ] == networkpolicy["spec"]["ingress"][0]["from"]

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
        networkpolicy = docs[0]
        assert networkpolicy["kind"] == "NetworkPolicy"
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
        assert "vector.$remote_user.*" in es_index

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
        assert "vector.$remote_user.*" in es_index

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
        assert doc["spec"]["rules"][0]["host"] == "es-proxy.plane.example.com"

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
        assert 'proxy_cache_key "$http_authorization"' in nginx_config
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
