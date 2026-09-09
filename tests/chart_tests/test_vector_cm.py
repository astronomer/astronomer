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

    def test_vector_configmap_has_airflow_3_task_logs_source(self, kube_version):
        """Test that vector configmap includes airflow_3_task_logs source for kubelet directory."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]

        assert "airflow_3_task_logs:" in config_yaml
        assert "type: file" in config_yaml
        assert "/var/lib/kubelet/pods/*/volumes/kubernetes.io~empty-dir/logs/**/*.log" in config_yaml
        assert "read_from: beginning" in config_yaml
        assert 'strategy: "checksum"' in config_yaml
        assert "max_line_bytes: 102400" in config_yaml

    def test_vector_configmap_has_airflowV2_kubernetes_logs_source(self, kube_version):
        """Test that vector configmap includes airflow_k8s_logs source for kubernetes_logs."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]

        assert "airflow_k8s_logs:" in config_yaml
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
        assert "airflow_3_task_logs" in config_yaml

        assert ".kubernetes.pod_uid = pod_uid" in config_yaml
        assert ".pod_uid_for_lookup = pod_uid" in config_yaml
        assert '.log_source = "airflow_3_file"' in config_yaml

        assert "parsed = parse_json(.message)" in config_yaml

    def test_vector_configmap_merge_logs_receives_file_logs_pipeline(self, kube_version):
        """Test that merge_logs receives enrich_file_logs and not enrich_k8s_logs."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]

        assert "merge_logs:" in config_yaml
        assert "type: remap" in config_yaml

        config_dict = yaml.safe_load(config_yaml)
        merge_logs_inputs = config_dict["transforms"]["merge_logs"]["inputs"]

        assert "enrich_file_logs" in merge_logs_inputs, "AF3 file logs should feed into merge_logs"
        assert "enrich_k8s_logs" not in merge_logs_inputs, "enrich_k8s_logs should not be an input to merge_logs"

    def test_vector_configmap_no_enrich_k8s_logs_transform(self, kube_version):
        """Test that the enrich_k8s_logs transform is not present in the vector config."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]

        assert "enrich_k8s_logs:" not in config_yaml

        config_dict = yaml.safe_load(config_yaml)
        assert "enrich_k8s_logs" not in config_dict.get("transforms", {})

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

    def test_vector_configmap_parse_json_messages_normalizes_level_to_string(self, kube_version):
        """Test that parse_json_messages transform normalizes integer level to string."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]

        config_dict = yaml.safe_load(config_yaml)
        source = config_dict["transforms"]["parse_json_messages"]["source"]

        assert "is_integer(.level)" in source
        assert ".level = to_string!(.level)" in source

    def test_vector_configmap_filters_task_logs_out_of_k8s_logs_pipeline(self, kube_version):
        """AF3 tasks write each line to both stdout and attempt=N.log, so the stdout
        pipeline must drop the duplicate before the shared elasticsearch sink."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        config_yaml = doc["data"]["vector-config.yaml"]
        config_dict = yaml.safe_load(config_yaml)
        transforms = config_dict["transforms"]

        assert "filter_k8s_task_logs:" in config_yaml
        assert transforms["filter_k8s_task_logs"]["type"] == "filter"
        assert transforms["filter_k8s_task_logs"]["inputs"] == ["transform_task_logs"]
        assert transforms["filter_k8s_task_logs"]["condition"]["type"] == "vrl"
        assert transforms["transform_add_timestamp"]["inputs"] == ["filter_k8s_task_logs"]

    def test_vector_configmap_k8s_task_log_filter_requires_full_task_identity(self, kube_version):
        """The log_type tag is set on the mere presence of a dag_id, which scheduler and
        dag-processor lines also carry. Keying the drop off it loses those from both
        pipelines, so the filter must require full task identity."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        config_dict = yaml.safe_load(docs[0]["data"]["vector-config.yaml"])
        source = config_dict["transforms"]["filter_k8s_task_logs"]["condition"]["source"]

        assert "is_task_output = exists(.dag_id) && exists(.task_id) && exists(.run_id)" in source
        # The loose log_type tag must not be what decides the drop.
        assert '.log_type != "task"' not in source

    def test_vector_configmap_k8s_task_log_filter_exempts_kubernetes_executor_pods(self, kube_version):
        """KubernetesExecutor task pods name their logs emptyDir "logs", not
        "logs-<release>", so their file copy is indexed as <prefix>.unknown.* and never
        read. The stdout copy is the only readable one and must survive the drop."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        config_dict = yaml.safe_load(docs[0]["data"]["vector-config.yaml"])
        source = config_dict["transforms"]["filter_k8s_task_logs"]["condition"]["source"]

        assert "is_kubernetes_executor_pod = exists(.kubernetes.pod_labels.dag_id)" in source
        assert "!is_task_output || is_kubernetes_executor_pod" in source

    def test_vector_configmap_file_pipeline_drops_unresolvable_release(self, kube_version):
        """extract_release falls back to "unknown" when the path has no "logs-<release>"
        segment. Those events would be indexed as <prefix>.unknown.* and never read, and
        the stdout pipeline already carries them with correct pod labels."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        config_dict = yaml.safe_load(docs[0]["data"]["vector-config.yaml"])
        condition = config_dict["transforms"]["filter_task_logs_only"]["condition"]

        assert condition["type"] == "vrl"
        assert '.log_type == "task" && .release != "unknown"' in condition["source"]
