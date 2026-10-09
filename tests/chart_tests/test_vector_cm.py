import re

import pytest
import yaml

from tests import supported_k8s_versions
from tests.chart_tests.conftest import docker_daemon_present
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
        assert 'endpoints: ["http://release-name-elasticsearch:9200"]' in config_yaml

        # Verify index pattern includes release
        assert 'index: "fluentd.{{ .release }}.%Y.%m.%d"' in config_yaml
        assert "action: create" in config_yaml

        # Verify bulk settings
        assert "mode: bulk" in config_yaml
        assert "max_bytes: 10485760" in config_yaml

    def test_vector_configmap_elasticsearch_sink_uses_external_proxy(self, kube_version):
        """Test that custom logging renders the external Elasticsearch proxy endpoint."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"customLogging": {"enabled": True}}},
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        assert len(docs) == 1
        config_yaml = docs[0]["data"]["vector-config.yaml"]
        assert 'endpoints: ["http://release-name-external-es-proxy:9201"]' in config_yaml

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

    def test_vector_configmap_k8s_task_log_filter_drops_only_ke_task_pod_output(self, kube_version):
        """The duplicate is the KubernetesExecutor task pod's stdout copy, whose file
        copy resolves a release and carries a log_id. Both halves of the condition are
        required: without is_ke_task_pod the drop also takes Celery worker stdout, and
        without is_task_output it takes the KE pod's non-task lines."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        config_dict = yaml.safe_load(docs[0]["data"]["vector-config.yaml"])
        source = config_dict["transforms"]["filter_k8s_task_logs"]["condition"]["source"]

        assert "is_ke_task_pod = exists(.kubernetes.pod_labels.dag_id)" in source
        assert "is_task_output = exists(.dag_id) && exists(.task_id) && exists(.run_id)" in source
        assert "!(is_ke_task_pod && is_task_output)" in source

    def test_vector_configmap_k8s_task_log_filter_keys_on_pod_label_not_payload(self, kube_version):
        """Scheduler, dag-processor and triggerer lines about a task instance carry
        dag_id/task_id/run_id in their payload, and their file-sourced equivalent is
        dropped as dag_parse. Only the pod label distinguishes a KE task pod, so the
        drop must not be decided by the payload field or the log_type tag alone."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        config_dict = yaml.safe_load(docs[0]["data"]["vector-config.yaml"])
        source = config_dict["transforms"]["filter_k8s_task_logs"]["condition"]["source"]

        assert ".kubernetes.pod_labels.dag_id" in source
        assert '.log_type != "task"' not in source

    def test_vector_configmap_file_pipeline_ships_all_task_logs(self, kube_version):
        """The file pipeline is authoritative for task logs and must not filter on a
        resolved release: extract_release returns "unknown" for every logs-named volume,
        which on operator-managed deployments includes the Celery worker."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )

        config_dict = yaml.safe_load(docs[0]["data"]["vector-config.yaml"])
        condition = config_dict["transforms"]["filter_task_logs_only"]["condition"]

        assert condition == '.log_type == "task"'


# The ap-vector image sets VECTOR_DANGEROUSLY_ALLOW_ENV_VAR_INTERPOLATION=true as a stopgap, so
# `vector validate` would accept any ${VAR} reference. Rendered configs must not contain any:
# sink credentials are read through Vector's secrets backend (SECRET[...]) instead.
_ENV_TOKEN = re.compile(r"\$\{[^{}]+\}")


@pytest.mark.skipif(not docker_daemon_present(), reason="Docker daemon not available")
@pytest.mark.parametrize(
    "sink_values",
    [
        pytest.param({"elasticsearch": {"enabled": True, "endpoint": "http://127.0.0.1:9200"}}, id="elasticsearch"),
        pytest.param({"cloudwatch": {"enabled": True, "region": "us-east-2", "useIRSA": False}}, id="cloudwatch-static-keys"),
    ],
)
def test_rendered_vector_configs_validate_with_the_rendered_image(docker_client, tmp_path, sink_values):
    manifests = render_chart(values={"astronomer": {"houston": {"logging": {"loggingSidecar": {"enabled": True, **sink_values}}}}})

    configs = [
        config
        for manifest in manifests
        if manifest.get("kind") == "ConfigMap"
        for key, config in manifest.get("data", {}).items()
        if key in {"vector-config.yaml", "vector.yaml"}
        if isinstance(config, str)
        and (parsed := yaml.safe_load(config))
        and isinstance(parsed, dict)
        and "sources" in parsed
        and "sinks" in parsed
    ]
    assert len(configs) == 3, f"Expected daemonset, Houston API, and Houston worker Vector configs; found {len(configs)}"

    images = {
        container["image"]
        for manifest in manifests
        for container in manifest.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        if container.get("name") == "vector"
    }
    assert len(images) == 1, f"Expected one rendered Vector image, found: {images}"
    image = images.pop()

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    for index, config in enumerate(configs):
        references = set(_ENV_TOKEN.findall(config))
        assert not references, f"Unexpected Vector environment references: {references}"

        validation_config = yaml.safe_load(config)
        validation_config["data_dir"] = "/vector-data"
        for sink in validation_config["sinks"].values():
            if isinstance(sink.get("healthcheck"), dict):
                sink["healthcheck"]["enabled"] = False

        config_path = config_dir / f"vector-{index}.yaml"
        config_path.write_text(yaml.safe_dump(validation_config))
        docker_client.containers.run(
            image,
            entrypoint="vector",
            command=["validate", "--no-environment"],
            environment={
                "VECTOR_CONFIG": f"/vector-config/vector-{index}.yaml",
            },
            volumes={
                str(config_dir): {"bind": "/vector-config", "mode": "ro"},
                str(data_dir): {"bind": "/vector-data", "mode": "rw"},
            },
            remove=True,
        )
