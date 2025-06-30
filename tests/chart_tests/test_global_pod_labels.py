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
        """Helper to get nested dictionary value using dot notation path.

        Example:
            path = "spec.template.metadata.labels" returns obj["spec"]["template"]["metadata"]["labels"]
        """
        keys = path.split(".")
        current = obj
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return None

    def _extract_pod_labels_data(self, docs: list) -> dict:
        """Helper method to extract pod labels from rendered chart documents.

        Returns a dictionary mapping resource names to their labels.
        """
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

            pod_docs.append({"name": name, "kind": kind, "labels": pod_labels})

        return {f"{doc['kind']}_{doc['name']}": doc["labels"] for doc in pod_docs}

    def init_test_global_pod_labels(self, kube_version: str) -> dict:
        """Initialize test data for global pod labels functionality.

        Return a dictionary mapping of k8s manifest names to their pod labels."""
        chart_values = chart_tests.get_all_features()
        chart_values["global"]["podLabels"] = {
            "fake_label_1": "fake_value_1",
            "fake_label_2": "fake_value_2",
        }

        docs = render_chart(values=chart_values, kube_version=kube_version)
        return self._extract_pod_labels_data(docs)

    def test_global_pod_labels_applied(self, kube_version: str):
        """Test that global pod labels are applied to all pod-creating resources."""
        test_data = self.init_test_global_pod_labels(kube_version)

        for resource_name, pod_labels in test_data.items():
            assert pod_labels is not None, f"Pod labels should not be None for {resource_name}"

            assert "fake_label_1" in pod_labels, f"fake_label_1 missing in {resource_name}"
            assert pod_labels["fake_label_1"] == "fake_value_1", f"fake_label_1 value incorrect in {resource_name}"
            assert "fake_label_2" in pod_labels, f"fake_label_2 missing in {resource_name}"
            assert pod_labels["fake_label_2"] == "fake_value_2", f"fake_label_2 value incorrect in {resource_name}"

            # Standard labels in the "Software" platform
            assert "tier" in pod_labels, f"tier label missing in {resource_name}"
            assert "component" in pod_labels, f"component label missing in {resource_name}"
            assert "release" in pod_labels, f"release label missing in {resource_name}"

    def test_global_pod_labels_do_not_affect_non_pod_resources(self, kube_version: str):
        """Test that global pod labels are not applied to non-pod resources."""
        chart_values = chart_tests.get_all_features()
        chart_values["global"]["podLabels"] = {"should-not-appear": "on-services-or-configmaps"}

        docs = render_chart(values=chart_values, kube_version=kube_version)

        for doc in docs:
            kind = doc.get("kind")
            if kind in {"Service", "ConfigMap", "Secret"}:
                labels = doc.get("metadata", {}).get("labels", {})
                assert "should-not-appear" not in labels, f"Pod labels should not appear on {kind} {doc['metadata']['name']}"

    def test_global_pod_labels_merge_with_existing_labels(self, kube_version: str):
        """Test that global pod labels merge correctly with existing component labels."""
        chart_values = chart_tests.get_all_features()
        chart_values["global"] = {"podLabels": {"global-label": "global-value"}}

        docs = render_chart(values=chart_values, kube_version=kube_version)

        deployments = [doc for doc in docs if doc.get("kind") == "Deployment"]

        assert deployments, "At least one deployment should be found"

        for deployment in deployments:
            labels = deployment["spec"]["template"]["metadata"]["labels"]
            deployment_name = deployment["metadata"]["name"]

            assert "global-label" in labels, f"global-label missing in deployment {deployment_name}"
            assert labels["global-label"] == "global-value", f"global-label value incorrect in deployment {deployment_name}"

            # Standard labels in the "Software" platform
            assert "tier" in labels, f"tier label missing in deployment {deployment_name}"
            assert "component" in labels, f"component label missing in deployment {deployment_name}"
            assert "release" in labels, f"release label missing in deployment {deployment_name}"
