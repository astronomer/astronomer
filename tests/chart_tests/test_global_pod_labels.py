import jmespath
import pytest

import tests.chart_tests as chart_tests
from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestGlobalPodLabels:
    """Test class for global pod labels functionality across different Kubernetes versions."""

    KUBERNETES_POD_OBJECTS = {
        "StatefulSet": "spec.template.metadata.labels",
        "Deployment": "spec.template.metadata.labels",
        "CronJob": "spec.jobTemplate.spec.template.metadata.labels",
        "Job": "spec.template.metadata.labels",
        "DaemonSet": "spec.template.metadata.labels",
        "Pod": "metadata.labels",
    }

    def _get_nested_value(self, obj, path):
        """Helper to get nested dictionary value using dot notation path."""
        keys = path.split(".")
        current = obj
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return None

    def _extract_pod_labels_data(self, docs):
        """Helper method to extract pod labels from rendered chart documents."""
        pod_docs = []

        for doc in docs:
            if not isinstance(doc, dict) or "kind" not in doc or "metadata" not in doc:
                continue

            kind = doc["kind"]

            if kind not in self.KUBERNETES_POD_OBJECTS:
                continue
            labels_path = self.KUBERNETES_POD_OBJECTS[kind]
            pod_labels = self._get_nested_value(doc, labels_path)

            if pod_labels is None:
                continue

            metadata = doc.get("metadata", {})
            name = metadata.get("name", "unknown")
            chart = metadata.get("labels", {}).get("chart", "None")

            pod_docs.append({"name": name, "kind": kind, "chart": chart, "labels": pod_labels})

        return {f"{doc['chart']}_{doc['kind']}_{doc['name']}": doc["labels"] for doc in pod_docs}

    def init_test_global_pod_labels(self, kube_version):
        """Initialize test data for global pod labels functionality."""
        chart_values = chart_tests.get_all_features()
        chart_values["global"] = {
            "podLabels": {"gatekeeper.policy": "approved", "security.level": "high", "cost-center": "engineering"}
        }

        docs = render_chart(values=chart_values, kube_version=kube_version)
        return self._extract_pod_labels_data(docs)

    def init_test_global_pod_labels_disabled(self, kube_version):
        """Initialize test data when global pod labels are not configured."""
        chart_values = chart_tests.get_all_features()
        docs = render_chart(values=chart_values, kube_version=kube_version)
        return self._extract_pod_labels_data(docs)

    def test_global_pod_labels_applied(self, kube_version):
        """Test that global pod labels are applied to all pod-creating resources."""
        test_data = self.init_test_global_pod_labels(kube_version)

        for resource_name, pod_labels in test_data.items():
            assert pod_labels is not None, f"Pod labels should not be None for {resource_name}"

            assert "gatekeeper.policy" in pod_labels, f"gatekeeper.policy missing in {resource_name}"
            assert pod_labels["gatekeeper.policy"] == "approved", f"gatekeeper.policy value incorrect in {resource_name}"

            assert "security.level" in pod_labels, f"security.level missing in {resource_name}"
            assert pod_labels["security.level"] == "high", f"security.level value incorrect in {resource_name}"

            assert "cost-center" in pod_labels, f"cost-center missing in {resource_name}"
            assert pod_labels["cost-center"] == "engineering", f"cost-center value incorrect in {resource_name}"

            assert "tier" in pod_labels, f"tier label missing in {resource_name}"
            assert "component" in pod_labels, f"component label missing in {resource_name}"
            assert "release" in pod_labels, f"release label missing in {resource_name}"

    def test_global_pod_labels_do_not_affect_non_pod_resources(self, kube_version):
        """Test that global pod labels are not applied to non-pod resources."""
        chart_values = chart_tests.get_all_features()
        chart_values["global"] = {"podLabels": {"should-not-appear": "on-services-or-configmaps"}}

        docs = render_chart(values=chart_values, kube_version=kube_version)

        services = jmespath.search("[?kind == `Service`]", docs)
        for service in services:
            service_labels = service.get("metadata", {}).get("labels", {})
            assert "should-not-appear" not in service_labels, (
                f"Pod labels should not appear on Service {service['metadata']['name']}"
            )

        configmaps = jmespath.search("[?kind == `ConfigMap`]", docs)
        for cm in configmaps:
            cm_labels = cm.get("metadata", {}).get("labels", {})
            assert "should-not-appear" not in cm_labels, f"Pod labels should not appear on ConfigMap {cm['metadata']['name']}"

        secrets = jmespath.search("[?kind == `Secret`]", docs)
        for secret in secrets:
            secret_labels = secret.get("metadata", {}).get("labels", {})
            assert "should-not-appear" not in secret_labels, f"Pod labels should not appear on Secret {secret['metadata']['name']}"

    def test_global_pod_labels_merge_with_existing_labels(self, kube_version):
        """Test that global pod labels merge correctly with existing component labels."""
        chart_values = chart_tests.get_all_features()
        chart_values["global"] = {"podLabels": {"global-label": "global-value"}}

        docs = render_chart(values=chart_values, kube_version=kube_version)

        deployments = jmespath.search("[?kind == `Deployment`]", docs)

        assert len(deployments) > 0, "At least one deployment should be found"

        for deployment in deployments:
            labels = deployment["spec"]["template"]["metadata"]["labels"]
            deployment_name = deployment["metadata"]["name"]

            assert "global-label" in labels, f"global-label missing in deployment {deployment_name}"
            assert labels["global-label"] == "global-value", f"global-label value incorrect in deployment {deployment_name}"

            assert "tier" in labels, f"tier label missing in deployment {deployment_name}"
            assert "component" in labels, f"component label missing in deployment {deployment_name}"
            assert "release" in labels, f"release label missing in deployment {deployment_name}"
