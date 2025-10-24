import pytest
import yaml
from tests import (
    get_containers_by_name,
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
        assert "persistentVolumeClaimRetentionPolicy" not in docs[0]["spec"]

        # elasticsearch data
        assert docs[1]["kind"] == "StatefulSet"
        esd_containers = get_containers_by_name(docs[1], include_init_containers=True)
        assert vm_max_map_count in esd_containers["sysctl"]["command"]
        assert "persistentVolumeClaimRetentionPolicy" not in docs[1]["spec"]

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
            assert doc["spec"]["template"]["spec"]["securityContext"] == {"fsGroup": 1000}

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
                "charts/elasticsearch/templates/nginx/nginx-es-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert "NetworkPolicy" == doc["kind"]
        assert [
            {
                "namespaceSelector": {},
                "podSelector": {"matchLabels": {"tier": "airflow", "component": "webserver"}},
            },
        ] == doc["spec"]["ingress"][0]["from"]

    def test_nginx_es_client_network_selector_with_logging_sidecar_enabled(self, kube_version):
        """Test Nginx ES Service with NetworkPolicies."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"loggingSidecar": {"enabled": True}}},
            show_only=[
                "charts/elasticsearch/templates/nginx/nginx-es-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert "NetworkPolicy" == doc["kind"]
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
        assert "client_max_body_size 100M" in nginx_config

    def test_elastic_nginx_config_custom_max_body_size(self, kube_version):
        """Test that custom max body size is properly set."""
        docs = render_chart(
            kube_version=kube_version,
            values={"elasticsearch": {"nginx": {"maxBodySize": "123456789M"}}},
            show_only=[
                "charts/elasticsearch/templates/nginx/nginx-es-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        nginx_config = " ".join(doc["data"]["nginx.conf"].split())
        assert "client_max_body_size 123456789M" in nginx_config

    def test_elastic_nginx_config_pattern_defaults_and_index_prefix_overrides(self, kube_version):
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

    def test_elasticsearch_nginx_config_pattern_with_sidecar_logging_enabled(self, kube_version):
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

    def test_elasticsearch_nginx_config_pattern_with_sidecar_logging_enabled_and_index_prefix_overrides(self, kube_version):
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
            show_only=["charts/elasticsearch/templates/exporter/es-exporter-deployment.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        pod_data = doc["spec"]["template"]["spec"]

        assert pod_data["securityContext"] == {}

        assert pod_data["containers"][0]["securityContext"] == {
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
        }

    def test_elasticsearch_exporter_securitycontext_overrides(self, kube_version):
        """Test ElasticSearch Exporter with securityContext default values."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "exporter": {
                        "podSecurityContext": {"runAsNonRoot": True},
                        "securityContext": {"runAsNonRoot": True, "runAsUser": 2000},
                    }
                }
            },
            show_only=["charts/elasticsearch/templates/exporter/es-exporter-deployment.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        pod_data = doc["spec"]["template"]["spec"]
        assert pod_data["securityContext"]["runAsNonRoot"] is True
        assert pod_data["containers"][0]["securityContext"]["runAsNonRoot"] is True
        assert pod_data["containers"][0]["securityContext"]["runAsUser"] == 2000

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
        assert node_master_roles_env in docs[0]["spec"]["template"]["spec"]["containers"][0]["env"]
        node_data_roles_env = {
            "name": "node.roles",
            "value": "data,data_cold,data_content,data_frozen,data_hot,data_warm,ml,remote_cluster_client,transform,",
        }
        assert node_data_roles_env in docs[1]["spec"]["template"]["spec"]["containers"][0]["env"]
        node_client_roles_env = {
            "name": "node.roles",
            "value": "ingest,ml,remote_cluster_client,",
        }
        assert node_client_roles_env in docs[2]["spec"]["template"]["spec"]["containers"][0]["env"]

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
        assert node_master_roles_env in docs[0]["spec"]["template"]["spec"]["containers"][0]["env"]
        node_data_roles_env = {
            "name": "node.roles",
            "value": "data,",
        }
        assert node_data_roles_env in docs[1]["spec"]["template"]["spec"]["containers"][0]["env"]
        node_client_roles_env = {
            "name": "node.roles",
            "value": "ingest,",
        }
        assert node_client_roles_env in docs[2]["spec"]["template"]["spec"]["containers"][0]["env"]

    def test_elasticsearch_curator_indexPatterns_override_with_loggingSidecar(self, kube_version):
        """Test ElasticSearch Curator IndexPattern Override with loggingSidecar"""
        indexPattern = "%Y.%m"
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"loggingSidecar": {"enabled": True, "indexPattern": indexPattern}}},
            show_only=["charts/elasticsearch/templates/curator/es-curator-configmap.yaml"],
        )
        assert len(docs) == 1
        LS = yaml.safe_load(docs[0]["data"]["action_file.yml"])
        assert indexPattern == LS["actions"][1]["filters"][0]["timestring"]

    def test_elasticsearch_curator_with_indexPatterns_defaults(self, kube_version):
        """Test ElasticSearch Curator IndexPattern with defaults"""
        indexPattern = "%Y.%m.%d"
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/elasticsearch/templates/curator/es-curator-configmap.yaml"],
        )
        assert len(docs) == 1
        LS = yaml.safe_load(docs[0]["data"]["action_file.yml"])
        assert indexPattern == LS["actions"][1]["filters"][0]["timestring"]

    def test_elasticsearch_curator_config_defaults(self, kube_version):
        """Test ElasticSearch Curator IndexPattern with defaults"""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/elasticsearch/templates/curator/es-curator-configmap.yaml"],
        )
        assert len(docs) == 1
        LS = yaml.safe_load(docs[0]["data"]["config.yml"])
        assert "elasticsearch" in LS
        assert "http://release-name-elasticsearch:9200" in LS["elasticsearch"]["client"]["hosts"]

    def test_elasticsearch_curator_config_overrides(self, kube_version):
        """Test ElasticSearch Curator IndexPattern with defaults"""
        docs = render_chart(
            kube_version=kube_version,
            values={"elasticsearch": {"common": {"protocol": "https"}}},
            show_only=["charts/elasticsearch/templates/curator/es-curator-configmap.yaml"],
        )
        assert len(docs) == 1
        LS = yaml.safe_load(docs[0]["data"]["config.yml"])
        assert "elasticsearch" in LS
        assert "https://release-name-elasticsearch:9200" in LS["elasticsearch"]["client"]["hosts"]

    def test_elasticsearch_curator_cronjob_defaults(self, kube_version):
        """Test ElasticSearch Curator cron job with nodeSelector, affinity, tolerations and config defaults"""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/elasticsearch/templates/curator/es-curator-cronjob.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert docs[0]["kind"] == "CronJob"
        assert docs[0]["metadata"]["name"] == "release-name-elasticsearch-curator"
        assert docs[0]["spec"]["schedule"] == "0 1 * * *"
        spec = docs[0]["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        assert spec["nodeSelector"] == {}
        assert spec["affinity"] == {}
        assert spec["tolerations"] == []
        assert c_by_name["curator"]["command"] == ["/bin/sh", "-c"]
        assert c_by_name["curator"]["args"] == [
            "sleep 5; /usr/bin/curator --config /etc/config/config.yml /etc/config/action_file.yml; exit_code=$?; wget --timeout=5 -O- --post-data='not=used' http://127.0.0.1:15020/quitquitquit; exit $exit_code;"
        ]
        assert c_by_name["curator"]["securityContext"] == {}

    def test_elasticsearch_curator_cronjob_overrides(self, kube_version, global_platform_node_pool_config):
        """Test ElasticSearch Curator cron job with nodeSelector, affinity, tolerations and config overrides."""
        values = {
            "elasticsearch": {
                "curator": {
                    "schedule": "0 45 * * *",
                    "securityContext": {"runAsNonRoot": True},
                }
            },
            "global": {
                "platformNodePool": global_platform_node_pool_config,
            },
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/elasticsearch/templates/curator/es-curator-cronjob.yaml"],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "CronJob"
        assert docs[0]["metadata"]["name"] == "release-name-elasticsearch-curator"
        assert docs[0]["spec"]["schedule"] == "0 45 * * *"
        spec = docs[0]["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        assert spec["nodeSelector"]["role"] == "astro"
        assert len(spec["affinity"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["global"]["platformNodePool"]["tolerations"]
        c_by_name = get_containers_by_name(docs[0])
        assert c_by_name["curator"]["command"] == ["/bin/sh", "-c"]
        assert c_by_name["curator"]["args"] == [
            "sleep 5; /usr/bin/curator --config /etc/config/config.yml /etc/config/action_file.yml; exit_code=$?; wget --timeout=5 -O- --post-data='not=used' http://127.0.0.1:15020/quitquitquit; exit $exit_code;"
        ]
        assert c_by_name["curator"]["securityContext"] == {"runAsNonRoot": True}

    def test_elasticsearch_curator_cronjob_subchart_overrides(self, kube_version, global_platform_node_pool_config):
        """Test ElasticSearch Curator cron job with nodeSelector, affinity, tolerations and config overrides."""
        global_platform_node_pool_config["nodeSelector"] = {"role": "astroelasticsearch"}
        values = {
            "elasticsearch": {
                "curator": {
                    "schedule": "0 45 * * *",
                    "securityContext": {"runAsNonRoot": True},
                },
                "nodeSelector": global_platform_node_pool_config["nodeSelector"],
                "affinity": global_platform_node_pool_config["affinity"],
                "tolerations": global_platform_node_pool_config["tolerations"],
            },
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/elasticsearch/templates/curator/es-curator-cronjob.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert docs[0]["kind"] == "CronJob"
        assert docs[0]["metadata"]["name"] == "release-name-elasticsearch-curator"
        assert docs[0]["spec"]["schedule"] == "0 45 * * *"
        spec = docs[0]["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        assert spec["nodeSelector"]["role"] == "astroelasticsearch"
        assert len(spec["affinity"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["elasticsearch"]["tolerations"]
        assert c_by_name["curator"]["command"] == ["/bin/sh", "-c"]
        assert c_by_name["curator"]["args"] == [
            "sleep 5; /usr/bin/curator --config /etc/config/config.yml /etc/config/action_file.yml; exit_code=$?; wget --timeout=5 -O- --post-data='not=used' http://127.0.0.1:15020/quitquitquit; exit $exit_code;"
        ]
        assert c_by_name["curator"]["securityContext"] == {"runAsNonRoot": True}

    def test_elasticsearch_nginx_deployment_defaults(self, kube_version):
        """Test ElasticSearch Nginx deployment default values."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/elasticsearch/templates/nginx/nginx-es-deployment.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert c_by_name["nginx"]["securityContext"] == {}

    def test_elasticsearch_nginx_deployment_overrides(self, kube_version):
        """Test ElasticSearch Nginx deployment default overrides."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {"nginx": {"securityContext": {"runAsNonRoot": True}}},
            },
            show_only=["charts/elasticsearch/templates/nginx/nginx-es-deployment.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert c_by_name["nginx"]["securityContext"] == {"runAsNonRoot": True}

    def test_elasticsearch_persistentVolumeClaimRetentionPolicy(self, kube_version):
        test_persistentVolumeClaimRetentionPolicy = {
            "whenDeleted": "Delete",
            "whenScaled": "Retain",
        }
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "common": {
                        "persistence": {
                            "persistentVolumeClaimRetentionPolicy": test_persistentVolumeClaimRetentionPolicy,
                        },
                    },
                },
            },
            show_only=[
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
            ],
        )

        assert len(docs) == 2

        for doc in docs:
            assert "persistentVolumeClaimRetentionPolicy" in doc["spec"]
            assert test_persistentVolumeClaimRetentionPolicy == doc["spec"]["persistentVolumeClaimRetentionPolicy"]

    def test_elasticsearch_statefulset_with_scc_disabled(self, kube_version):
        """Test that helm renders scc template for astronomer
        elasticsearch with SA disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/elasticsearch/templates/es-scc.yaml",
            ],
        )
        assert len(docs) == 0

    def test_elasticsearch_statefulset_with_scc_enabled(self, kube_version):
        """Test that helm renders scc template for astronomer
        elasticsearch with SA disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"sccEnabled": True}},
            show_only=[
                "charts/elasticsearch/templates/es-scc.yaml",
            ],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "SecurityContextConstraints"
        assert docs[0]["apiVersion"] == "security.openshift.io/v1"
        assert docs[0]["metadata"]["name"] == "release-name-elasticsearch-anyuid"
        assert docs[0]["users"] == ["system:serviceaccount:default:release-name-elasticsearch"]

    def test_elasticsearch_nginx_auth_cache_enabled_by_default(self, kube_version):
        """Test that auth caching is enabled by default in nginx-es configmap."""
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

    def test_elasticsearch_nginx_auth_cache_disabled(self, kube_version):
        """Test that auth caching can be disabled in nginx-es configmap."""
        docs = render_chart(
            kube_version=kube_version,
            values={"elasticsearch": {"nginx": {"authCache": {"enabled": False}}}},
            show_only=[
                "charts/elasticsearch/templates/nginx/nginx-es-configmap.yaml",
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

    def test_elasticsearch_nginx_auth_cache_custom_settings(self, kube_version):
        """Test that custom auth cache settings are properly rendered."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "nginx": {
                        "authCache": {
                            "enabled": True,
                            "path": "/custom/cache/path",
                            "levels": "2:2",
                            "keysZone": "custom_cache:20m",
                            "maxSize": "200m",
                            "inactive": "10m",
                            "validSuccess": "10m",
                            "validFailure": "2m",
                        }
                    }
                }
            },
            show_only=[
                "charts/elasticsearch/templates/nginx/nginx-es-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"

        nginx_config = doc["data"]["nginx.conf"]

        # Verify custom cache path settings
        assert "proxy_cache_path /custom/cache/path" in nginx_config
        assert "levels=2:2" in nginx_config
        assert "keys_zone=custom_cache:20m" in nginx_config
        assert "max_size=200m" in nginx_config
        assert "inactive=10m" in nginx_config

        # Verify custom TTL settings
        assert "proxy_cache_valid 200 10m" in nginx_config
        assert "proxy_cache_valid 401 403 2m" in nginx_config
