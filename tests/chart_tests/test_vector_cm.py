"""
Test suite for Vector ConfigMap Airflow 2 and Airflow 3 log pipelines.
Tests for the re-added Kubernetes enrichment and unified log processing.
"""

import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestVectorConfigmap:
    """Test suite for Airflow 2 and Airflow 3 log processing pipelines."""

    def test_vector_configmap_has_airflow3_file_logs_source(self, kube_version):
        """Test that vector configmap includes airflow3_file_logs source for kubelet directory."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]

        assert "airflow3_file_logs:" in config_yaml
        assert "type: file" in config_yaml
        assert "/var/lib/kubelet/pods/*/volumes/kubernetes.io~empty-dir/logs/**/*.log" in config_yaml
        assert "read_from: beginning" in config_yaml
        assert 'strategy: "checksum"' in config_yaml
        assert "max_line_bytes: 102400" in config_yaml

    def test_vector_configmap_has_airflow2_kubernetes_logs_source(self, kube_version):
        """Test that vector configmap includes airflow2_log_files source for kubernetes_logs."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]

        assert "airflow2_log_files:" in config_yaml
        assert "type: kubernetes_logs" in config_yaml
        assert "auto_partial_merge: true" in config_yaml

    def test_vector_configmap_has_enrich_file_logs_transform(self, kube_version):
        """Test that enrich_file_logs transform extracts pod_uid and parses JSON."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]

        assert "enrich_file_logs:" in config_yaml
        assert "type: remap" in config_yaml
        assert "airflow3_file_logs" in config_yaml

        assert ".kubernetes.pod_uid = pod_uid" in config_yaml
        assert ".pod_uid_for_lookup = pod_uid" in config_yaml
        assert '.log_source = "airflow3_file"' in config_yaml

        assert "parsed = parse_json(.message)" in config_yaml

    def test_vector_configmap_merge_logs_receives_both_pipelines(self, kube_version):
        """Test that merge_logs consolidates both AF2 and AF3 processed logs."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]

        # Verify merge_logs exists
        assert "merge_logs:" in config_yaml
        assert "type: remap" in config_yaml

        # Verify it receives inputs from both pipelines
        config_dict = yaml.safe_load(config_yaml)
        merge_logs_inputs = config_dict["transforms"]["merge_logs"]["inputs"]

        assert "enrich_file_logs" in merge_logs_inputs, "AF3 file logs should feed into merge_logs"
        assert "enrich_k8s_logs" in merge_logs_inputs, "AF2 processed logs should feed into merge_logs"

    def test_vector_configmap_filter_by_component_keeps_airflow_components(self, kube_version):
        """Test that filter_by_component keeps only Airflow components."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]

        # Verify component filter exists
        assert "filter_by_component:" in config_yaml
        assert "type: filter" in config_yaml

        # Verify all expected Airflow components are in the filter
        expected_components = [
            "scheduler",
            "webserver",
            "api-server",
            "worker",
            "triggerer",
            "git-sync-relay",
            "dag-server",
            "airflow-downgrade",
            "meta-cleanup",
            "dag-processor",
        ]

        for component in expected_components:
            assert f'"{component}"' in config_yaml or f"'{component}'" in config_yaml

    def test_vector_configmap_elasticsearch_sink_uses_release_index(self, kube_version):
        """Test that Elasticsearch sink creates indexes with release name."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]

        # Verify Elasticsearch sink
        assert "elasticsearch:" in config_yaml
        assert "type: elasticsearch" in config_yaml
        assert 'endpoints: ["http://${ELASTICSEARCH_HOST}:${ELASTICSEARCH_PORT}"]' in config_yaml

        # Verify index pattern includes release
        assert 'index: "fluentd.{{ .release }}.%Y.%m.%d"' in config_yaml
        assert "action: create" in config_yaml

        # Verify bulk settings
        assert "mode: bulk" in config_yaml
        assert "max_bytes: 10485760" in config_yaml
