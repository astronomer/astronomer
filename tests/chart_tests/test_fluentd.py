from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions, get_containers_by_name
import jmespath
import yaml


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestFluentd:

    @staticmethod
    def fluentd_common_tests(doc):
        """Test common for fluentd daemonsets."""
        assert doc["kind"] == "DaemonSet"
        assert doc["metadata"]["name"] == "release-name-fluentd"

    def test_fluentd_daemonset(self, kube_version):
        """Test that helm renders a volume mount for private ca certificates for
        fluentd daemonset when private-ca-certificates are enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"privateCaCerts": ["private-root-ca"]}},
            show_only=["charts/fluentd/templates/fluentd-daemonset.yaml"],
        )

        search_result = jmespath.search(
            "spec.template.spec.containers[*].volumeMounts[?name == 'private-root-ca']",
            docs[0],
        )
        expected_result = [
            [
                {
                    "mountPath": "/usr/local/share/ca-certificates/private-root-ca.pem",
                    "name": "private-root-ca",
                    "subPath": "cert.pem",
                }
            ]
        ]
        assert search_result == expected_result
        search_result_es_index_template_volume_mount = jmespath.search(
            "spec.template.spec.containers[*].volumeMounts[?name == 'release-name-fluentd-index-template-volume']",
            docs[0],
        )

        expected_result_es_index_template_volume_mount = [
            [
                {
                    "mountPath": "/host",
                    "name": "release-name-fluentd-index-template-volume",
                    "readOnly": True,
                }
            ]
        ]

        assert search_result_es_index_template_volume_mount == expected_result_es_index_template_volume_mount

        search_result_es_index_template_volume = jmespath.search(
            "spec.template.spec.volumes[?name == 'release-name-fluentd-index-template-volume']",
            docs[0],
        )

        expected_result_es_index_template_volume = [
            {
                "name": "release-name-fluentd-index-template-volume",
                "configMap": {"name": "release-name-fluentd-index-template-configmap"},
            }
        ]

        assert search_result_es_index_template_volume == expected_result_es_index_template_volume

    def test_fluentd_clusterrolebinding(self, kube_version):
        """Test that helm renders a good ClusterRoleBinding template for fluentd
        when rbacEnabled=True."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"rbacEnabled": True}},
            show_only=["charts/fluentd/templates/fluentd-clusterrolebinding.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ClusterRoleBinding"
        assert doc["apiVersion"] == "rbac.authorization.k8s.io/v1"
        assert doc["metadata"]["name"] == "release-name-fluentd"
        assert len(doc["roleRef"]) > 0
        assert len(doc["subjects"]) > 0

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"rbacEnabled": False}},
            show_only=["charts/fluentd/templates/fluentd-clusterrolebinding.yaml"],
        )
        assert len(docs) == 0

    def test_fluentd_configmap_manual_namespaces_enabled(self, kube_version):
        """Test that when namespace Pools is disabled, and manualNamespaces is
        enabled, helm renders fluentd configmap targeting all namespaces."""
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "manualNamespaceNamesEnabled": True,
                    "features": {
                        "namespacePools": {
                            "enabled": False,
                        }
                    },
                }
            },
            show_only=["charts/fluentd/templates/fluentd-configmap.yaml"],
        )[0]

        expected_rule = "key $.kubernetes.namespace_name\n    # fluentd should gather logs from all namespaces if manualNamespaceNamesEnabled is enabled"
        assert expected_rule in doc["data"]["output.conf"]

    def test_fluentd_configmap_manual_namespaces_and_namespacepools_disabled(self, kube_version):
        """Test that when namespace Pools and manualNamespaceNamesEnabled are
        disabled, helm renders a default fluentd configmap looking at an
        environment variable."""
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "manualNamespaceNamesEnabled": False,
                    "features": {
                        "namespacePools": {
                            "enabled": False,
                        }
                    },
                }
            },
            show_only=["charts/fluentd/templates/fluentd-configmap.yaml"],
        )[0]

        expected_rule = 'key $.kubernetes.namespace_labels.platform\n    pattern "release-name"'
        assert expected_rule in doc["data"]["output.conf"]

    def test_fluentd_configmap_configure_extra_log_stores(self, kube_version):
        """Test that when namespace Pools and manualNamespaceNamesEnabled are
        disabled, helm renders a default fluentd configmap looking at an
        environment variable."""
        doc = render_chart(
            kube_version=kube_version,
            values={
                "fluentd": {
                    "extraLogStores": """
<store>
  @type newrelic
  @log_level info
  base_uri https://log-api.newrelic.com/log/v1
  license_key <LICENSE_KEY>
  <buffer>
    @type memory
    flush_interval 5s
  </buffer>
</store>
                    """
                }
            },
            show_only=["charts/fluentd/templates/fluentd-configmap.yaml"],
        )[0]
        expected_store = "  <store>\n    @type newrelic\n    @log_level info\n    base_uri https://log-api.newrelic.com/log/v1\n    license_key <LICENSE_KEY>"
        assert expected_store in doc["data"]["output.conf"]

    def test_fluentd_pod_securityContextOverride(self, kube_version):
        """Test that helm renders a container securityContext when securityContext
        is enabled."""

        docs = render_chart(
            kube_version=kube_version,
            values={"fluentd": {"pod": {"securityContext": {"runAsUser": 9999}}}},
            show_only=["charts/fluentd/templates/fluentd-daemonset.yaml"],
        )

        pod_search_result = jmespath.search(
            "spec.template.spec",
            docs[0],
        )
        # the pod container should report a default user of 9999
        assert pod_search_result["securityContext"]["runAsUser"] == 9999

    def test_fluentd_container_securityContextOverride(self, kube_version):
        """Test that helm renders a container securityContext when securityContext
        is enabled."""

        docs = render_chart(
            kube_version=kube_version,
            values={
                "fluentd": {
                    "container": {
                        "securityContext": {
                            "runAsUser": 8888,
                            "seLinuxOptions": {"type": "spc_t"},
                        }
                    }
                }
            },
            show_only=["charts/fluentd/templates/fluentd-daemonset.yaml"],
        )

        container_search_result = jmespath.search(
            "spec.template.spec.containers[?name == 'fluentd']",
            docs[0],
        )
        # the fluentd container should now report running as user 8888
        assert container_search_result[0]["securityContext"]["runAsUser"] == 8888

    def test_fluentd_securityContext_empty_by_default(self, kube_version):
        """Test that no securityContext is present by default on pod or
        container."""

        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/fluentd/templates/fluentd-daemonset.yaml"],
        )

        container_search_result = jmespath.search(
            "spec.template.spec.containers[?name == 'fluentd']",
            docs[0],
        )
        pod_search_result = jmespath.search(
            "spec.template.spec",
            docs[0],
        )
        # the securityContext should be present but empty by default
        assert not pod_search_result["securityContext"].keys()
        # the securityContext should be present but empty by default
        assert not container_search_result[0]["securityContext"].keys()

    def test_fluentd_index_defaults(self, kube_version):
        """Test to validate fluentd index name prefix defaults in fluentd configmap."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"rbacEnabled": True}},
            show_only=[
                "charts/fluentd/templates/fluentd-configmap.yaml",
                "charts/fluentd/templates/fluentd-index-template-configmap.yaml",
            ],
        )

        assert len(docs) == 2
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-fluentd"
        assert 'fluentd.${record["release"]}.${Time.at(time).getutc.strftime(@logstash_dateformat)}' in doc["data"]["output.conf"]
        doc = docs[1]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-fluentd-index-template-configmap"
        index_cm = yaml.safe_load(doc["data"]["index_template.json"])
        assert index_cm == {
            "index_patterns": ["fluentd.*"],
            "mappings": {"properties": {"date_nano": {"type": "date_nanos"}}},
        }

    def test_fluentd_index_overrides(self, kube_version):
        """Test to validate fluentd index name prefix defaults in fluentd configmap."""
        indexNamePrefix = "astronomer"
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"logging": {"indexNamePrefix": indexNamePrefix}}},
            show_only=[
                "charts/fluentd/templates/fluentd-configmap.yaml",
                "charts/fluentd/templates/fluentd-index-template-configmap.yaml",
            ],
        )

        assert len(docs) == 2
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-fluentd"
        assert (
            'astronomer.${record["release"]}.${Time.at(time).getutc.strftime(@logstash_dateformat)}' in doc["data"]["output.conf"]
        )

        doc = docs[1]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-fluentd-index-template-configmap"
        index_cm = yaml.safe_load(doc["data"]["index_template.json"])
        assert index_cm == {
            "index_patterns": ["astronomer.*"],
            "mappings": {"properties": {"date_nano": {"type": "date_nanos"}}},
        }

    def test_fluentd_priorityclass_defaults(self, kube_version):
        """Test to validate fluentd with priority class defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/fluentd/templates/fluentd-daemonset.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        self.fluentd_common_tests(doc)
        assert "priorityClassName" not in doc["spec"]["template"]["spec"]

    def test_fluentd_priorityclass_overrides(self, kube_version):
        """Test to validate fluentd with priority class configured."""
        docs = render_chart(
            kube_version=kube_version,
            values={"fluentd": {"priorityClassName": "fluentd-priority-pod"}},
            show_only=["charts/fluentd/templates/fluentd-daemonset.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        self.fluentd_common_tests(doc)
        assert "priorityClassName" in doc["spec"]["template"]["spec"]
        assert "fluentd-priority-pod" == doc["spec"]["template"]["spec"]["priorityClassName"]

    def test_fluentd_with_custom_env(self, kube_version):
        """Test to validate fluentd extraEnv configured."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "fluentd": {
                    "extraEnv": {"RUBY_GC_HEAP_OLDOBJECT_LIMIT_FACTOR": 1},
                },
            },
            show_only=["charts/fluentd/templates/fluentd-daemonset.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        self.fluentd_common_tests(doc)
        assert {
            "name": "RUBY_GC_HEAP_OLDOBJECT_LIMIT_FACTOR",
            "value": "1",
        } in c_by_name[
            "fluentd"
        ]["env"]

    def test_fluentd_daemonset_probe(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/fluentd/templates/fluentd-daemonset.yaml"],
        )
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        assert c_by_name["fluentd"]["name"] == "fluentd"
        liveness_probe = c_by_name["fluentd"]["livenessProbe"]
        assert liveness_probe["failureThreshold"] == 3
        assert liveness_probe["initialDelaySeconds"] == 30
        assert liveness_probe["periodSeconds"] == 15
        assert liveness_probe["successThreshold"] == 1
        assert liveness_probe["timeoutSeconds"] == 5

    def test_fluentd_configmap_disable_manage_cluster_scoped_resources(self, kube_version):
        """Test that with disable_manage_cluster_scoped_resources, helm renders fluentd configmap targeting all namespaces."""
        doc = render_chart(
            kube_version=kube_version,
            values={"global": {"disableManageClusterScopedResources": True}},
            show_only=["charts/fluentd/templates/fluentd-configmap.yaml"],
        )[0]

        expected_rule = "key $.kubernetes.namespace_name\n    # fluentd should gather logs from all namespaces if manualNamespaceNamesEnabled is enabled"
        assert expected_rule in doc["data"]["output.conf"]
