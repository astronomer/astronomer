import pytest
import yaml

from tests import git_root_dir, supported_k8s_versions
from tests.utils import (
    get_containers_by_name,
)
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestElasticSearch:
    def test_elasticsearch_defaults(self, kube_version):
        """Test ElasticSearch default behaviors."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/elasticsearch/templates/curator/es-curator-cronjob.yaml",
                "charts/elasticsearch/templates/client/es-client-deployment.yaml",
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
                "charts/elasticsearch/templates/nginx/nginx-es-deployment.yaml",
            ],
        )

        vm_max_map_count = "vm.max_map_count=262144"
        assert len(docs) == 5

        curator_doc, client_doc, data_doc, master_doc, nginx_doc = docs

        # elasticsearch curator
        assert curator_doc["kind"] == "CronJob"
        assert curator_doc["metadata"]["name"] == "release-name-elasticsearch-curator"
        assert curator_doc["spec"]["schedule"] == "0 1 * * *"

        curator_pod = curator_doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        assert not curator_pod.get("nodeSelector")
        assert not curator_pod.get("affinity")
        assert not curator_pod.get("tolerations")

        curator_containers = get_containers_by_name(curator_doc, include_init_containers=True)
        assert len(curator_containers) == 1

        curator_container = curator_containers["curator"]
        assert curator_container.get("volumeMounts") == [{"name": "config-volume", "mountPath": "/etc/config"}]
        assert curator_container["command"] == ["/bin/sh", "-c"]
        assert curator_container["args"] == [
            "sleep 5; /usr/bin/curator --config /etc/config/config.yml /etc/config/action_file.yml; exit_code=$?; wget --timeout=5 -O- --post-data='not=used' http://127.0.0.1:15020/quitquitquit; exit $exit_code;"
        ]
        assert curator_container["securityContext"] == {"readOnlyRootFilesystem": True, "runAsNonRoot": True}

        # elasticsearch master
        assert master_doc["kind"] == "StatefulSet"
        es_master_containers = get_containers_by_name(master_doc, include_init_containers=True)
        assert len(es_master_containers) == 3
        assert vm_max_map_count in es_master_containers["sysctl"]["command"]
        assert "persistentVolumeClaimRetentionPolicy" not in master_doc["spec"]
        assert es_master_containers["es-master"]["volumeMounts"] == [
            {"name": "tmp", "mountPath": "/tmp"},
            {"name": "es-config-dir", "mountPath": "/usr/share/elasticsearch/config"},
            {"name": "tmp", "subPath": "logs", "mountPath": "/usr/share/elasticsearch/logs"},
            {"name": "data", "mountPath": "/usr/share/elasticsearch/data"},
            {"name": "config", "subPath": "elasticsearch.yml", "mountPath": "/usr/share/elasticsearch/config/elasticsearch.yml"},
        ]
        # elasticsearch data
        assert data_doc["kind"] == "StatefulSet"
        es_data_containers = get_containers_by_name(data_doc, include_init_containers=True)
        assert len(es_data_containers) == 3
        assert vm_max_map_count in es_data_containers["sysctl"]["command"]
        assert "persistentVolumeClaimRetentionPolicy" not in data_doc["spec"]
        assert es_data_containers["es-data"]["volumeMounts"] == [
            {"name": "tmp", "mountPath": "/tmp"},
            {"name": "es-config-dir", "mountPath": "/usr/share/elasticsearch/config"},
            {"name": "tmp", "subPath": "logs", "mountPath": "/usr/share/elasticsearch/logs"},
            {"name": "data", "mountPath": "/usr/share/elasticsearch/data"},
            {"name": "config", "subPath": "elasticsearch.yml", "mountPath": "/usr/share/elasticsearch/config/elasticsearch.yml"},
        ]

        # elasticsearch client
        assert client_doc["kind"] == "Deployment"
        es_client_containers = get_containers_by_name(client_doc, include_init_containers=True)
        assert len(es_client_containers) == 3
        assert vm_max_map_count in es_client_containers["sysctl"]["command"]
        assert es_client_containers["es-client"]["volumeMounts"] == [
            {"mountPath": "/tmp", "name": "tmp"},
            {"mountPath": "/usr/share/elasticsearch/config", "name": "es-config-dir"},
            {"mountPath": "/usr/share/elasticsearch/data", "name": "es-data"},
            {"mountPath": "/usr/share/elasticsearch/logs", "name": "es-client-logs"},
            {"mountPath": "/usr/share/elasticsearch/config/elasticsearch.yml", "name": "config", "subPath": "elasticsearch.yml"},
        ]

        assert es_client_containers["es-config-dir-copier"]["volumeMounts"] == [
            {"name": "es-config-dir", "mountPath": "/usr/share/elasticsearch/config_copy"},
        ]

        assert es_client_containers["es-config-dir-copier"]["image"] == es_client_containers["es-client"]["image"]
        assert es_client_containers["es-client"]["image"].startswith("quay.io/astronomer/ap-elasticsearch:")

        # elasticsearch nginx
        assert nginx_doc["kind"] == "Deployment"
        esn_containers = get_containers_by_name(nginx_doc, include_init_containers=True)
        assert len(esn_containers) == 1
        assert esn_containers["nginx"]["volumeMounts"] == [
            {"name": "tmp", "mountPath": "/tmp"},
            {"name": "var-cache-nginx", "mountPath": "/var/cache/nginx"},
            {"name": "nginx-config-volume", "mountPath": "/etc/nginx"},
        ]

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
            assert all("sysctl" not in x["name"] for x in doc["spec"]["template"]["spec"].get("initContainers") or [])

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
                            "snoopy": "dog",
                            "woodstock": "bird",
                        },
                    },
                    "securityContext": {
                        "denver": "colorado",
                        "detroit": "michigan",
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
        assert pod_data["securityContext"] == {
            "readOnlyRootFilesystem": True,
            "snoopy": "dog",
            "woodstock": "bird",
        }

    def test_elasticsearch_data_securitycontext_overrides(self, kube_version):
        """Test ElasticSearch client with securityContext custom values."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "data": {
                        "securityContext": {
                            "snoopy": "dog",
                            "woodstock": "bird",
                        },
                    },
                    "securityContext": {
                        "denver": "colorado",
                        "detroit": "michigan",
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
        assert pod_data["securityContext"] == {"readOnlyRootFilesystem": True, "snoopy": "dog", "woodstock": "bird"}

    def test_elasticsearch_client_securitycontext_overrides(self, kube_version):
        """Test ElasticSearch client with securityContext custom values."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "client": {
                        "securityContext": {
                            "snoopy": "dog",
                            "woodstock": "bird",
                        },
                    },
                    "securityContext": {
                        "denver": "colorado",
                        "detroit": "michigan",
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
        assert pod_data["securityContext"] == {"readOnlyRootFilesystem": True, "snoopy": "dog", "woodstock": "bird"}

    def test_elasticsearch_securitycontext_overrides(self, kube_version):
        """Test ElasticSearch master, data with securityContext custom
        values."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "securityContext": {
                        "denver": "colorado",
                        "detroit": "michigan",
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
            container_data = doc["spec"]["template"]["spec"]["containers"][0]
            # Assert that container_data["securityContext"] contains at least the listed dict items
            assert (
                container_data["securityContext"].items()
                >= {
                    "readOnlyRootFilesystem": True,
                    "capabilities": {"drop": ["ALL"]},
                    "denver": "colorado",
                    "detroit": "michigan",
                    "runAsNonRoot": True,
                    "runAsUser": 1000,
                }.items()
            )

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
                "location ~* /_bulk$ { rewrite /_bulk(.*) /fluentd.$remote_user.*/_bulk$1 break;",
                "location ~* /_count$ { rewrite /_count(.*) /fluentd.$remote_user.*/_count$1 break;",
                "location ~* /_search$ { rewrite /_search(.*) /fluentd.$remote_user.*/_search$1 break;",
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
                        "podSecurityContext": {
                            "denver": "colorado",
                            "detroit": "michigan",
                        },
                        "securityContext": {
                            "snoopy": "dog",
                            "woodstock": "bird",
                        },
                    }
                }
            },
            show_only=["charts/elasticsearch/templates/exporter/es-exporter-deployment.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        pod_data = doc["spec"]["template"]["spec"]
        assert pod_data["securityContext"] == {"denver": "colorado", "detroit": "michigan"}
        assert pod_data["containers"][0]["securityContext"] == {
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
            "snoopy": "dog",
            "woodstock": "bird",
        }

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

    def test_elasticsearch_curator_cronjob_overrides(self, kube_version, global_platform_node_pool_config):
        """Test ElasticSearch Curator cron job with nodeSelector, affinity, tolerations and config overrides."""
        values = {
            "elasticsearch": {
                "curator": {
                    "schedule": "0 45 * * *",
                    "securityContext": {
                        "snoopy": "dog",
                        "woodstock": "bird",
                    },
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
        assert len(c_by_name) == 1
        curator_container = c_by_name["curator"]
        assert curator_container["command"] == ["/bin/sh", "-c"]
        assert curator_container["args"] == [
            "sleep 5; /usr/bin/curator --config /etc/config/config.yml /etc/config/action_file.yml; exit_code=$?; wget --timeout=5 -O- --post-data='not=used' http://127.0.0.1:15020/quitquitquit; exit $exit_code;"
        ]
        assert curator_container["securityContext"] == {
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "snoopy": "dog",
            "woodstock": "bird",
        }

    def test_elasticsearch_curator_cronjob_subchart_overrides(self, kube_version, global_platform_node_pool_config):
        """Test ElasticSearch Curator cron job with nodeSelector, affinity, tolerations and config overrides."""
        global_platform_node_pool_config["nodeSelector"] = {"role": "astroelasticsearch"}
        values = {
            "elasticsearch": {
                "curator": {
                    "schedule": "0 45 * * *",
                    "securityContext": {
                        "snoopy": "dog",
                        "woodstock": "bird",
                    },
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
        assert len(c_by_name) == 1
        curator_container = c_by_name["curator"]
        assert curator_container["command"] == ["/bin/sh", "-c"]
        assert curator_container["args"] == [
            "sleep 5; /usr/bin/curator --config /etc/config/config.yml /etc/config/action_file.yml; exit_code=$?; wget --timeout=5 -O- --post-data='not=used' http://127.0.0.1:15020/quitquitquit; exit $exit_code;"
        ]
        assert curator_container["securityContext"] == {
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "snoopy": "dog",
            "woodstock": "bird",
        }

    def test_elasticsearch_nginx_deployment_defaults(self, kube_version):
        """Test ElasticSearch Nginx deployment default values."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/elasticsearch/templates/nginx/nginx-es-deployment.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert c_by_name["nginx"]["securityContext"] == {"readOnlyRootFilesystem": True, "runAsNonRoot": True}

    def test_elasticsearch_nginx_deployment_overrides(self, kube_version):
        """Test ElasticSearch Nginx deployment default overrides."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "elasticsearch": {
                    "nginx": {
                        "securityContext": {
                            "snoopy": "dog",
                            "woodstock": "bird",
                        }
                    }
                },
            },
            show_only=["charts/elasticsearch/templates/nginx/nginx-es-deployment.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert c_by_name["nginx"]["securityContext"] == {
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "snoopy": "dog",
            "woodstock": "bird",
        }

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

    es_component_templates = [
        str(path.relative_to(git_root_dir)) for path in list(git_root_dir.glob("charts/elasticsearch/templates/*/*.yaml"))
    ]

    @pytest.mark.parametrize("doc", es_component_templates)
    @pytest.mark.parametrize("plane_mode,should_render", [("data", True), ("unified", True), ("control", False)])
    def test_elasticsearch_templates_render_in_data_and_unified_mode(self, kube_version, doc, plane_mode, should_render):
        """Test that elasticsearch templates are not rendered in control or unified plane modes."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": plane_mode}}, "elasticsearch": {"data": {"persistence": {"enabled": True}}}},
            show_only=[doc],
        )
        if should_render:
            assert len(docs) == 1, f"Document {doc} should render in {plane_mode} mode"
        else:
            assert len(docs) == 0, f"Document {doc} should not render in {plane_mode} mode"

    def test_elasticsearch_ingress_control_mode_default(self, kube_version):
        """Test that helm renders a correct Elasticsearch ingress template in data plane mode"""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=["charts/elasticsearch/templates/es-ingress.yaml"],
        )
        assert len(docs) == 0
        # doc = docs[0]
        # assert doc["kind"] == "Ingress"
        # assert doc["metadata"]["name"] == "release-name-elasticsearch-ingress"
        # assert doc["metadata"]["labels"]["component"] == "elasticsearch-logging-ingress"
        # assert doc["metadata"]["labels"]["tier"] == "elasticsearch-networking"
        # assert doc["metadata"]["labels"]["plane"] == "data"

    # @pytest.mark.parametrize("plane_mode", ["control", "unified"])
    # def test_elasticsearch_ingress_disabled_when_data_mode_is_disabled(self, kube_version, plane_mode):
    #    """Test that helm does not render Elasticsearch ingress in control plane mode."""
    #    docs = render_chart(
    #        kube_version=kube_version,
    #        values={
    #            "global": {
    #                "plane": {"mode": plane_mode},
    #            }
    #        },
    #        show_only=["charts/elasticsearch/templates/es-ingress.yaml"],
    #    )
    #    assert len(docs) == 0

    @pytest.mark.parametrize("plane_mode", ["data", "unified"])
    def test_elasticsearch_ingress(self, kube_version, plane_mode):
        """Test elasticsearch ingress configuration"""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/elasticsearch/templates/es-ingress.yaml"],
            values={"global": {"baseDomain": "example.com"}, "plane": {"mode": plane_mode}},
        )

        print(docs)

        assert len(docs) == 1, f"Document {docs} should render in {plane_mode} mode"
        assert docs[0]["kind"] == "Ingress"
        assert docs[0]["apiVersion"] == "networking.k8s.io/v1"
        annotations = docs[0]["metadata"]["annotations"]
        auth_annotations = ["nginx.ingress.kubernetes.io/auth-signin", "nginx.ingress.kubernetes.io/auth-response-headers"]
        for auth_annotation in auth_annotations:
            assert auth_annotation not in annotations
        rules = docs[0]["spec"]["rules"]
        assert len(rules) == 1
        paths = rules[0]["http"]["paths"]
        assert len(paths) == 1
        assert paths[0]["path"] == "/"
        assert paths[0]["pathType"] == "Prefix"
        backend = paths[0]["backend"]
        assert backend["service"] == {"name": "release-name-elasticsearch", "port": {"number": 9200}}
