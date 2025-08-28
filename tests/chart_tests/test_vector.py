from pathlib import Path

import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart

all_templates = list(Path("charts/vector/templates").glob("*.yaml"))


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestVector:
    @staticmethod
    def vector_daemonset_common_tests(doc):
        """Test common for vector daemonsets."""
        assert doc["kind"] == "DaemonSet"
        assert doc["metadata"]["name"] == "release-name-vector"

    def test_vector_defaults_when_enabled(self, kube_version):
        """Test that vector behaves as expected with default values when it is enabled."""
        values = {"global": {"logging": {"collector": "vector"}}}
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=all_templates,
        )
        assert len(docs) == 6
        assert all(doc.get("apiVersion") for doc in docs)
        assert all(doc.get("kind") for doc in docs)

    @pytest.mark.skip("TODO: revisit this.")
    def test_vector_daemonset_private_ca_certificates(self, kube_version):
        """Test that helm renders a volume mount for private ca certificates for vector daemonset when private-ca-certificates are enabled."""
        values = {
            "global": {"logging": {"collector": "vector"}},
            "privateCaCerts": ["private-root-ca"],
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/vector/templates/vector-daemonset.yaml"],
        )

        get_containers_by_name(docs[0])
        assert len(docs) == 1
        pod_spec = docs[0]["spec"]["template"]["spec"]
        assert len(pod_spec["volumes"]) == 2
        assert len(pod_spec["containers"]) == 1

        volume_mounts = [
            {"name": "varlog", "mountPath": "/var/log/", "readOnly": True},
            {"name": "config-volume-release-name-vector", "mountPath": "/etc/vector/config", "readOnly": True},
        ]
        assert pod_spec["containers"][0]["volumeMounts"] == volume_mounts

    def test_vector_clusterrolebinding(self, kube_version):
        """Test that helm renders a good ClusterRoleBinding template for vector when rbacEnabled=True."""
        values = {"global": {"rbacEnabled": True, "logging": {"collector": "vector"}}}
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/vector/templates/vector-clusterrolebinding.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ClusterRoleBinding"
        assert doc["apiVersion"] == "rbac.authorization.k8s.io/v1"
        assert doc["metadata"]["name"] == "release-name-vector"
        assert len(doc["roleRef"]) > 0
        assert len(doc["subjects"]) > 0

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"rbacEnabled": False}},
            show_only=["charts/vector/templates/vector-clusterrolebinding.yaml"],
        )
        assert len(docs) == 0

    def test_vector_configmap_manual_namespaces_enabled(self, kube_version):
        """Test that when namespace Pools is disabled, and manualNamespaces is enabled, helm renders a vector configmap targeting
        all namespaces."""
        values = {
            "global": {
                "logging": {"collector": "vector"},
                "manualNamespaceNamesEnabled": True,
                "features": {
                    "namespacePools": {
                        "enabled": False,
                    }
                },
            }
        }

        doc = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )[0]

        expected_rule = "match(.kubernetes.pod_namespace, r'^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')"
        assert expected_rule in doc["data"]["vector-config.yaml"]

    def test_vector_configmap_manual_namespaces_and_namespacepools_disabled(self, kube_version):
        """Test that when namespace Pools and manualNamespaceNamesEnabled are disabled, helm renders a default vector configmap
        looking at platform label."""
        values = {
            "global": {
                "manualNamespaceNamesEnabled": False,
                "logging": {"collector": "vector"},
                "features": {
                    "namespacePools": {
                        "enabled": False,
                    }
                },
            }
        }
        doc = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )[0]
        expected_rule = '.kubernetes.namespace_labels.platform == "release-name"'
        assert expected_rule in doc["data"]["vector-config.yaml"]

    def test_vector_securityContext_override(self, kube_version):
        """Test that helm renders a custom securityContext when securityContext is overridden."""

        values = {
            "global": {"logging": {"collector": "vector"}},
            "vector": {
                "podSecurityContext": {"happy": "family"},  # pod securityContext
                "vector": {"securityContext": {"runAsUser": 9999}},  # container securityContext
            },
        }

        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/vector/templates/vector-daemonset.yaml"],
        )
        assert len(docs) == 1

        pod_spec = docs[0]["spec"]["template"]["spec"]
        assert pod_spec["securityContext"] == {"happy": "family"}
        assert len(pod_spec["containers"]) == 1
        assert pod_spec["containers"][0]["securityContext"]["runAsUser"] == 9999

    def test_vector_securityContext_default(self, kube_version):
        """Test that we have the expected default security context for the vector container."""


        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/vector/templates/vector-daemonset.yaml"],
        )

        assert len(docs) == 1

        pod_spec = docs[0]["spec"]["template"]["spec"]
        assert pod_spec["securityContext"] == {}
        assert len(pod_spec["containers"]) == 1
        assert pod_spec["containers"][0]["securityContext"] == {"runAsUser": 0}

    def test_vector_index_defaults(self, kube_version):
        """Test to validate vector index name prefix defaults in vector configmap."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"logging": {"collector": "vector"}, "rbacEnabled": True}},
            show_only=[
                "charts/vector/templates/vector-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-vector"
        expected_index = 'index: "vector.{{ .release }}.%Y.%m.%d"'
        assert expected_index in doc["data"]["vector-config.yaml"]

    @pytest.mark.skip("TODO: revisit this test to see if we need this kind of thing with vector.")
    def test_vector_index_overrides(self, kube_version):
        """Test to validate vector index name prefix defaults in vector configmap."""
        indexNamePrefix = "astronomer"
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"logging": {"indexNamePrefix": indexNamePrefix}}},
            show_only=[
                "charts/vector/templates/vector-configmap.yaml",
                "charts/vector/templates/vector-index-template-configmap.yaml",
            ],
        )

        assert len(docs) == 2
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-vector"
        assert (
            'astronomer.${record["release"]}.${Time.at(time).getutc.strftime(@logstash_dateformat)}'
            in doc["data"]["vector-config.yaml"]
        )

        doc = docs[1]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-vector-index-template-configmap"
        index_cm = yaml.safe_load(doc["data"]["index_template.json"])
        assert index_cm == {
            "index_patterns": ["astronomer.*"],
            "mappings": {"properties": {"date_nano": {"type": "date_nanos"}}},
        }

    def test_vector_priorityclass_defaults(self, kube_version):
        """Test to validate vector with priority class defaults."""

        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-daemonset.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        self.vector_common_tests(doc)
        assert "priorityClassName" not in doc["spec"]["template"]["spec"]

    def test_vector_priorityclass_overrides(self, kube_version):
        """Test to validate vector with priority class configured."""

        values = {
            "vector": {"priorityClassName": "vector-priority-pod"},
        }

        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/vector/templates/vector-daemonset.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        self.vector_common_tests(doc)
        assert "priorityClassName" in doc["spec"]["template"]["spec"]
        assert "vector-priority-pod" == doc["spec"]["template"]["spec"]["priorityClassName"]

    def test_vector_with_custom_env(self, kube_version):
        """Test to validate vector extraEnv configured."""

        values = {
            "vector": {
                "extraEnv": {"AIRPLANE_QUOTE": "What's your vector, Victor?"},
            },
        }

        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/vector/templates/vector-daemonset.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        self.vector_common_tests(doc)
        assert {
            "name": "AIRPLANE_QUOTE",
            "value": "What's your vector, Victor?",
        } in c_by_name["vector"]["env"]

    def test_vector_daemonset_probe(self, kube_version):
        """Test the default probes for the vector daemonset."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-daemonset.yaml"],
        )
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        assert c_by_name["vector"]["name"] == "vector"
        expected_probe = {"httpGet": {"path": "/health", "port": 8686}, "initialDelaySeconds": 30, "periodSeconds": 10}
        assert c_by_name["vector"]["livenessProbe"] == expected_probe
        assert c_by_name["vector"]["readinessProbe"] == expected_probe
