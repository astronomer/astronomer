import pytest
import yaml
from tests import (
    get_containers_by_name,
    get_cronjob_containerspec_by_name,
    supported_k8s_versions,
)
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

        vm_max_map_count = "vm.max_map_count=262144"
        assert len(docs) == 3

        # elasticsearch master
        assert docs[0]["kind"] == "StatefulSet"
        esm_containers = get_containers_by_name(docs[0], include_init_containers=True)
        assert vm_max_map_count in esm_containers["sysctl"]["command"]

        # elasticsearch data
        assert docs[1]["kind"] == "StatefulSet"
        esd_containers = get_containers_by_name(docs[1], include_init_containers=True)
        assert vm_max_map_count in esd_containers["sysctl"]["command"]

        # elasticsearch client
        assert docs[2]["kind"] == "Deployment"
        esc_containers = get_containers_by_name(docs[1], include_init_containers=True)
        assert vm_max_map_count in esc_containers["sysctl"]["command"]

    def test_elasticsearch_with_sysctl_disabled(self, kube_version):
        """Test ElasticSearch master, data and client with sysctl
        config/values.yaml."""
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
        """Test ElasticSearch master, data and client with fsGroup default
        values."""
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
        """Test ElasticSearch master, data with securityContext default
        values."""
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

    def test_elasticsearch_master_securitycontext_overrides(self, kube_version):
        """Test ElasticSearch client with securityContext custom values."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "master": {
                        "securityContext": {
                            "capabilities": {"add": ["IPC_LOCK"]},
                        },
                    },
                    "securityContext": {
                        "capabilities": {"add": ["SYS_RESOURCE"]},
                    },
                }
            },
            show_only=[
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
            ],
        )
        assert len(docs) == 1
        doc = docs[0]
        pod_data = doc["spec"]["template"]["spec"]["containers"][0]
        assert pod_data["securityContext"]["capabilities"]["add"] == ["IPC_LOCK"]

    def test_elasticsearch_data_securitycontext_overrides(self, kube_version):
        """Test ElasticSearch client with securityContext custom values."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "data": {
                        "securityContext": {
                            "capabilities": {"add": ["IPC_LOCK"]},
                        },
                    },
                    "securityContext": {
                        "capabilities": {"add": ["SYS_RESOURCE"]},
                    },
                }
            },
            show_only=[
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
            ],
        )
        assert len(docs) == 1
        doc = docs[0]
        pod_data = doc["spec"]["template"]["spec"]["containers"][0]
        assert pod_data["securityContext"]["capabilities"]["add"] == ["IPC_LOCK"]

    def test_elasticsearch_client_securitycontext_overrides(self, kube_version):
        """Test ElasticSearch client with securityContext custom values."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "client": {
                        "securityContext": {
                            "capabilities": {"add": ["IPC_LOCK"]},
                        },
                    },
                    "securityContext": {
                        "capabilities": {"add": ["SYS_RESOURCE"]},
                    },
                }
            },
            show_only=[
                "charts/elasticsearch/templates/client/es-client-deployment.yaml",
            ],
        )
        assert len(docs) == 1
        doc = docs[0]
        pod_data = doc["spec"]["template"]["spec"]["containers"][0]
        assert pod_data["securityContext"]["capabilities"]["add"] == ["IPC_LOCK"]

    def test_elasticsearch_securitycontext_overrides(self, kube_version):
        """Test ElasticSearch master, data with securityContext custom
        values."""
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
            {
                "namespaceSelector": {},
                "podSelector": {
                    "matchLabels": {"component": "git-sync-relay", "tier": "airflow"}
                },
            },
        ] == doc["spec"]["ingress"][0]["from"]

    def test_elastic_nginx_config_pattern_defaults(self, kube_version):
        """Test External Elasticsearch Service Index Pattern Search
        defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/nginx/nginx-es-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"

        nginx_config = " ".join(doc["data"]["nginx.conf"].split())
        assert all(
            x in nginx_config
            for x in [
                "location ~* /_bulk$ { rewrite /_bulk(.*) /fluentd.$remote_user.*/_bulk$1 break;",
                "location ~* /_count$ { rewrite /_count(.*) /fluentd.$remote_user.*/_count$1 break;",
                "location ~* /_search$ { rewrite /_search(.*) /fluentd.$remote_user.*/_search$1 break;",
                "location = /_cluster/health { proxy_pass http://elasticsearch; }",
                "location = /_cluster/state/version { proxy_pass http://elasticsearch; }",
                "location ~ ^/ { deny all; } } }",
            ]
        )

    def test_elastic_nginx_config_pattern_defaults_and_index_prefix_overrides(
        self, kube_version
    ):
        """Test External Elasticsearch Service Index Pattern Search with index prefix overrides."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"logging": {"indexNamePrefix": "astronomer"}}},
            show_only=[
                "charts/elasticsearch/templates/nginx/nginx-es-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"

        nginx_config = " ".join(doc["data"]["nginx.conf"].split())
        assert all(
            x in nginx_config
            for x in [
                "location ~* /_bulk$ { rewrite /_bulk(.*) /astronomer.$remote_user.*/_bulk$1 break;",
                "location ~* /_count$ { rewrite /_count(.*) /astronomer.$remote_user.*/_count$1 break;",
                "location ~* /_search$ { rewrite /_search(.*) /astronomer.$remote_user.*/_search$1 break;",
                "location = /_cluster/health { proxy_pass http://elasticsearch; }",
                "location = /_cluster/state/version { proxy_pass http://elasticsearch; }",
                "location ~ ^/ { deny all; } } }",
            ]
        )

    def test_elasticsearch_nginx_config_pattern_with_sidecar_logging_enabled(
        self, kube_version
    ):
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
        assert doc["kind"] == "ConfigMap"

        nginx_config = " ".join(doc["data"]["nginx.conf"].split())
        assert all(
            x in nginx_config
            for x in [
                "location ~* /_bulk$ { rewrite /_bulk(.*) /vector.$remote_user.*/_bulk$1 break;",
                "location ~* /_count$ { rewrite /_count(.*) /vector.$remote_user.*/_count$1 break;",
                "location ~* /_search$ { rewrite /_search(.*) /vector.$remote_user.*/_search$1 break;",
                "location = /_cluster/health { proxy_pass http://elasticsearch; }",
                "location = /_cluster/state/version { proxy_pass http://elasticsearch; }",
                "location ~ ^/ { deny all; } } }",
            ]
        )

    def test_elasticsearch_nginx_config_pattern_with_sidecar_logging_enabled_and_index_prefix_overrides(
        self, kube_version
    ):
        """Test Nginx ES Service Index Pattern Search with sidecar logging."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "loggingSidecar": {"enabled": True},
                    "logging": {"indexNamePrefix": "astronomer"},
                }
            },
            show_only=[
                "charts/elasticsearch/templates/nginx/nginx-es-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"

        nginx_config = " ".join(doc["data"]["nginx.conf"].split())
        assert all(
            x in nginx_config
            for x in [
                "location ~* /_bulk$ { rewrite /_bulk(.*) /astronomer.$remote_user.*/_bulk$1 break;",
                "location ~* /_count$ { rewrite /_count(.*) /astronomer.$remote_user.*/_count$1 break;",
                "location ~* /_search$ { rewrite /_search(.*) /astronomer.$remote_user.*/_search$1 break;",
                "location = /_cluster/health { proxy_pass http://elasticsearch; }",
                "location = /_cluster/state/version { proxy_pass http://elasticsearch; }",
                "location ~ ^/ { deny all; } } }",
            ]
        )

    def test_elasticsearch_exporter_securitycontext_defaults(self, kube_version):
        """Test ElasticSearch Exporter with securityContext default values."""
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

        assert pod_data["securityContext"] is None

    def test_elasticsearch_exporter_securitycontext_overrides(self, kube_version):
        """Test ElasticSearch Exporter with securityContext default values."""
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

    def test_elasticsearch_role_defaults(self, kube_version):
        """Test ElasticSearch master, data and client with default roles"""
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
        node_master_roles_env = {
            "name": "node.roles",
            "value": "master,ml,remote_cluster_client,",
        }
        assert (
            node_master_roles_env
            in docs[0]["spec"]["template"]["spec"]["containers"][0]["env"]
        )
        node_data_roles_env = {
            "name": "node.roles",
            "value": "data,data_cold,data_content,data_frozen,data_hot,data_warm,ml,remote_cluster_client,transform,",
        }
        assert (
            node_data_roles_env
            in docs[1]["spec"]["template"]["spec"]["containers"][0]["env"]
        )
        node_client_roles_env = {
            "name": "node.roles",
            "value": "ingest,ml,remote_cluster_client,",
        }
        assert (
            node_client_roles_env
            in docs[2]["spec"]["template"]["spec"]["containers"][0]["env"]
        )

    def test_elasticsearch_role_overrides(self, kube_version):
        """Test ElasticSearch master, data and client with custom roles"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "master": {"roles": ["master"]},
                    "data": {"roles": ["data"]},
                    "client": {"roles": ["ingest"]},
                }
            },
            show_only=[
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
                "charts/elasticsearch/templates/client/es-client-deployment.yaml",
            ],
        )
        assert len(docs) == 3
        node_master_roles_env = {
            "name": "node.roles",
            "value": "master,",
        }
        assert (
            node_master_roles_env
            in docs[0]["spec"]["template"]["spec"]["containers"][0]["env"]
        )
        node_data_roles_env = {
            "name": "node.roles",
            "value": "data,",
        }
        assert (
            node_data_roles_env
            in docs[1]["spec"]["template"]["spec"]["containers"][0]["env"]
        )
        node_client_roles_env = {
            "name": "node.roles",
            "value": "ingest,",
        }
        assert (
            node_client_roles_env
            in docs[2]["spec"]["template"]["spec"]["containers"][0]["env"]
        )

    def test_elasticsearch_curator_indexPatterns_override_with_loggingSidecar(
        self, kube_version
    ):
        """Test ElasticSearch Curator IndexPattern Override with loggingSidecar"""
        indexPattern = "%Y.%m"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "loggingSidecar": {"enabled": True, "indexPattern": indexPattern}
                }
            },
            show_only=[
                "charts/elasticsearch/templates/curator/es-curator-configmap.yaml"
            ],
        )
        assert len(docs) == 1
        assert (LS := yaml.safe_load(docs[0]["data"]["action_file.yml"]))
        assert indexPattern == LS["actions"][1]["filters"][0]["timestring"]

    def test_elasticsearch_curator_with_indexPatterns_defaults(self, kube_version):
        """Test ElasticSearch Curator IndexPattern with defaults"""
        indexPattern = "%Y.%m.%d"
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/curator/es-curator-configmap.yaml"
            ],
        )
        assert len(docs) == 1
        assert (LS := yaml.safe_load(docs[0]["data"]["action_file.yml"]))
        assert indexPattern == LS["actions"][1]["filters"][0]["timestring"]

    def test_elasticsearch_curator_config_defaults(self, kube_version):
        """Test ElasticSearch Curator IndexPattern with defaults"""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/curator/es-curator-configmap.yaml"
            ],
        )
        assert len(docs) == 1
        assert (LS := yaml.safe_load(docs[0]["data"]["config.yml"]))
        print(LS["elasticsearch"])
        assert "elasticsearch" in LS
        assert (
            "http://release-name-elasticsearch:9200"
            in LS["elasticsearch"]["client"]["hosts"]
        )

    def test_elasticsearch_curator_config_overrides(self, kube_version):
        """Test ElasticSearch Curator IndexPattern with defaults"""
        docs = render_chart(
            kube_version=kube_version,
            values={"elasticsearch": {"common": {"protocol": "https"}}},
            show_only=[
                "charts/elasticsearch/templates/curator/es-curator-configmap.yaml"
            ],
        )
        assert len(docs) == 1
        assert (LS := yaml.safe_load(docs[0]["data"]["config.yml"]))
        print(LS["elasticsearch"])
        assert "elasticsearch" in LS
        assert (
            "https://release-name-elasticsearch:9200"
            in LS["elasticsearch"]["client"]["hosts"]
        )

    def test_elasticsearch_curator_cronjob_defaults(self, kube_version):
        """Test ElasticSearch Curator cron job with defaults"""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/curator/es-curator-cronjob.yaml"
            ],
        )
        assert len(docs) == 1
        c_by_name = get_cronjob_containerspec_by_name(docs[0])
        assert docs[0]["kind"] == "CronJob"
        assert docs[0]["metadata"]["name"] == "release-name-elasticsearch-curator"
        assert docs[0]["spec"]["schedule"] == "0 1 * * *"
        assert c_by_name["curator"]["command"] == ["/bin/sh", "-c"]
        assert c_by_name["curator"]["args"] == [
            "sleep 5; /usr/bin/curator --config /etc/config/config.yml /etc/config/action_file.yml; exit_code=$?; wget --timeout=5 -O- --post-data='not=used' http://127.0.0.1:15020/quitquitquit; exit $exit_code;"
        ]
        assert c_by_name["curator"]["securityContext"] == {}

    def test_elasticsearch_curator_cronjob_overrides(self, kube_version):
        """Test ElasticSearch Curator cron job with defaults"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "curator": {
                        "schedule": "0 45 * * *",
                        "securityContext": {"runAsNonRoot": True},
                    }
                }
            },
            show_only=[
                "charts/elasticsearch/templates/curator/es-curator-cronjob.yaml"
            ],
        )
        assert len(docs) == 1
        c_by_name = get_cronjob_containerspec_by_name(docs[0])
        assert docs[0]["kind"] == "CronJob"
        assert docs[0]["metadata"]["name"] == "release-name-elasticsearch-curator"
        assert docs[0]["spec"]["schedule"] == "0 45 * * *"
        assert c_by_name["curator"]["command"] == ["/bin/sh", "-c"]
        assert c_by_name["curator"]["args"] == [
            "sleep 5; /usr/bin/curator --config /etc/config/config.yml /etc/config/action_file.yml; exit_code=$?; wget --timeout=5 -O- --post-data='not=used' http://127.0.0.1:15020/quitquitquit; exit $exit_code;"
        ]
        assert c_by_name["curator"]["securityContext"] == {"runAsNonRoot": True}
