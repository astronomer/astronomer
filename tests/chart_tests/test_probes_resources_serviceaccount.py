import jmespath
import pytest
import tests.chart_tests as chart_tests
from tests.chart_tests.helm_template_generator import render_chart


def init_test_container_configs():
    """Initialize test data for container configurations (probes, resources, serviceAccountName)."""
    chart_values = chart_tests.get_all_features()
    kubernetes_objects = {
        "StatefulSet": {
            "containers_path": "spec.template.spec.containers",
            "init_containers_path": "spec.template.spec.initContainers",
            "service_account_path": "spec.template.spec.serviceAccountName",
        },
        "Deployment": {
            "containers_path": "spec.template.spec.containers",
            "init_containers_path": "spec.template.spec.initContainers",
            "service_account_path": "spec.template.spec.serviceAccountName",
        },
        "CronJob": {
            "containers_path": "spec.jobTemplate.spec.template.spec.containers",
            "init_containers_path": "spec.jobTemplate.spec.template.spec.initContainers",
            "service_account_path": "spec.jobTemplate.spec.template.spec.serviceAccountName",
        },
        "Job": {
            "containers_path": "spec.template.spec.containers",
            "init_containers_path": "spec.template.spec.initContainers",
            "service_account_path": "spec.template.spec.serviceAccountName",
        },
        "DaemonSet": {
            "containers_path": "spec.template.spec.containers",
            "init_containers_path": "spec.template.spec.initContainers",
            "service_account_path": "spec.template.spec.serviceAccountName",
        },
        "Pod": {
            "containers_path": "spec.containers",
            "init_containers_path": "spec.initContainers",
            "service_account_path": "spec.serviceAccountName",
        },
    }

    docs = render_chart(values=chart_values)
    test_data = {}

    for kind, paths in kubernetes_objects.items():
        base_query = f"[?kind == `{kind}`]"
        pod_objects = jmespath.search(base_query, docs)

        for pod_obj in pod_objects:
            chart_name = pod_obj.get("metadata", {}).get("labels", {}).get("chart", "unknown")
            pod_name = pod_obj.get("metadata", {}).get("name", "unknown")
            namespace = pod_obj.get("metadata", {}).get("namespace", "default")

            key = f"{chart_name}_{kind}_{pod_name}_{namespace}"

            service_account_name = jmespath.search(paths["service_account_path"], pod_obj)
            containers = jmespath.search(paths["containers_path"], pod_obj) or []
            init_containers = jmespath.search(paths["init_containers_path"], pod_obj) or []

            test_data[key] = {
                "pod": {
                    "name": pod_name,
                    "kind": kind,
                    "chart": chart_name,
                    "namespace": namespace,
                    "serviceAccountName": service_account_name,
                },
                "containers": containers,
                "initContainers": init_containers,
            }
    return test_data


test_container_configs_data = init_test_container_configs()


class TestContainerResourcesAndServiceAccount:
    """Test class for validating container resources and serviceAccountName across all Kubernetes objects."""

    @pytest.mark.parametrize(
        "config_data",
        test_container_configs_data.values(),
        ids=test_container_configs_data.keys(),
    )
    def test_pod_service_account_name(self, config_data):
        """Test that every pod has a serviceAccountName defined."""
        pod_data = config_data["pod"]
        service_account_name = pod_data["serviceAccountName"]

        assert service_account_name is not None, f"Pod {pod_data['name']} in chart {pod_data['chart']} missing serviceAccountName"
        assert service_account_name != "", f"Pod {pod_data['name']} in chart {pod_data['chart']} has empty serviceAccountName"
        assert isinstance(service_account_name, str), (
            f"Pod {pod_data['name']} in chart {pod_data['chart']} serviceAccountName must be a string"
        )

    @pytest.mark.parametrize(
        "config_data",
        test_container_configs_data.values(),
        ids=test_container_configs_data.keys(),
    )
    def test_containers_have_resources_section(self, config_data):
        """Test that every container has a resources section with limits and requests."""
        containers = config_data["containers"]
        pod_data = config_data["pod"]

        if not containers:
            pytest.skip(f"No containers found in {pod_data['kind']} {pod_data['name']} in chart {pod_data['chart']}")

        for i, container in enumerate(containers):
            container_name = container.get("name", f"container-{i}")

            assert "resources" in container, (
                f"Container '{container_name}' in {pod_data['kind']} {pod_data['name']} (chart: {pod_data['chart']}) missing resources key"
            )

            resources = container.get("resources", {})

            if not resources:
                continue

            limits = resources.get("limits", {})
            requests = resources.get("requests", {})

            assert limits or requests, (
                f"Container '{container_name}' in {pod_data['kind']} {pod_data['name']} (chart: {pod_data['chart']}) has resources section but missing both limits and requests"
            )

    @pytest.mark.parametrize(
        "config_data",
        [data for data in test_container_configs_data.values() if data["initContainers"]],
        ids=[key for key, data in test_container_configs_data.items() if data["initContainers"]],
    )
    def test_init_containers_have_resources_section(self, config_data):
        """Test that every init container has resources section with limits and requests."""
        init_containers = config_data["initContainers"]
        pod_data = config_data["pod"]

        for i, container in enumerate(init_containers):
            container_name = container.get("name", f"init-container-{i}")
            resources = container.get("resources", {})

            assert resources, (
                f"Init container '{container_name}' in {pod_data['kind']} {pod_data['name']} (chart: {pod_data['chart']}) missing resources section"
            )

            limits = resources.get("limits", {})
            assert limits, (
                f"Init container '{container_name}' in {pod_data['kind']} {pod_data['name']} (chart: {pod_data['chart']}) missing resource limits section"
            )

            requests = resources.get("requests", {})
            assert requests, (
                f"Init container '{container_name}' in {pod_data['kind']} {pod_data['name']} (chart: {pod_data['chart']}) missing resource requests section"
            )
