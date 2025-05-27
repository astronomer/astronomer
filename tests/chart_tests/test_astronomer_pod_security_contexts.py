import pytest
import yaml

from tests import git_root_dir
from tests.chart_tests.helm_template_generator import render_chart

include_kind_list = ["Deployment", "DaemonSet", "StatefulSet", "ReplicaSet", "Job", "CronJob"]

default_podsecuritycontext = {
    "fsGroup": 9999,
    "runAsGroup": 9998,
    "runAsUser": 7788,
}

default_containersecuritycontext = {
    "runAsNonRoot": True,
}

enable_all_podsecuritycontexts = yaml.safe_load(
    ((git_root_dir) / "tests" / "chart_tests" / "test_data" / "enable_all_podsecuritycontexts.yaml").read_text()
)


def find_all_pod_manager_templates() -> list[str]:
    """Return a sorted, unique list of all pod manager templates in the chart"""
    return sorted(
        {
            str(x.relative_to(git_root_dir))
            for x in (git_root_dir / "charts").rglob("*")
            if any(sub in x.name for sub in ("deployment", "statefulset", "replicaset", "daemonset", "job", "cronjob"))
        }
    )


def get_pod_spec_from_doc(doc):
    """Extract pod spec from different resource types."""
    kind = doc.get("kind")

    if kind in ["Deployment", "DaemonSet", "StatefulSet", "ReplicaSet"]:
        return doc.get("spec", {}).get("template", {}).get("spec", {})
    elif kind == "Job":
        return doc.get("spec", {}).get("template", {}).get("spec", {})
    elif kind == "CronJob":
        return doc.get("spec", {}).get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
    else:
        return {}


class TestSecurityContexts:
    """Test pod and container security context configuration for all pod manager templates."""

    docs = render_chart(values=enable_all_podsecuritycontexts)
    filtered_docs = [doc for doc in docs if doc.get("kind") in include_kind_list]
    job_docs = [doc for doc in docs if doc.get("kind") in ["Job", "CronJob"]]

    @pytest.mark.parametrize("doc", filtered_docs)
    def test_template_supports_podsecuritycontext(self, doc):
        """Test to ensure each pod manager template has support for podSecurityContext."""

        assert doc.get("kind") in include_kind_list, f"Unexpected document kind: {doc.get('kind')}"

        pod_spec = get_pod_spec_from_doc(doc)
        pod_security_context = pod_spec.get("securityContext")
        doc_name = doc.get("metadata", {}).get("name", "unknown")
        doc_kind = doc.get("kind")

        if not pod_security_context:
            print(f"No securityContext found in {doc_kind}/{doc_name}")
            print(f"Pod spec keys: {pod_spec.keys()}")

        assert pod_security_context is not None, f"No securityContext found in {doc_kind}/{doc_name}"

        assert "fsGroup" in pod_security_context, f"fsGroup not found in securityContext for {doc_kind}/{doc_name}"

        for key, value in default_podsecuritycontext.items():
            actual_value = pod_security_context.get(key)

            if actual_value != value:
                print(f"WARNING: {doc_kind}/{doc_name} - Expected {key}={value}, got {actual_value}")

            if key == "fsGroup":
                assert actual_value == value, f"Expected {key}={value} in securityContext, got {actual_value} for {doc_kind}/{doc_name}"

    @pytest.mark.parametrize("doc", filtered_docs)
    def test_template_supports_containersecuritycontext(self, doc):
        """Test to ensure each pod manager template has support for container securityContext."""

        assert doc.get("kind") in include_kind_list, f"Unexpected document kind: {doc.get('kind')}"

        pod_spec = get_pod_spec_from_doc(doc)
        containers = pod_spec.get("containers", [])
        doc_name = doc.get("metadata", {}).get("name", "unknown")
        doc_kind = doc.get("kind")

        assert containers, f"No containers found in {doc_kind}/{doc_name}"

        for i, container in enumerate(containers):
            container_name = container.get("name", f"container-{i}")
            container_security_context = container.get("securityContext")

            if not container_security_context:
                print(f"No securityContext found in container '{container_name}' of {doc_kind}/{doc_name}")
                print(f"Container keys: {container.keys()}")

            assert container_security_context is not None, f"No securityContext found in container '{container_name}' of {doc_kind}/{doc_name}"

            for key, expected_value in default_containersecuritycontext.items():
                actual_value = container_security_context.get(key)

                if actual_value != expected_value:
                    print(f"WARNING: {doc_kind}/{doc_name} container '{container_name}' - Expected {key}={expected_value}, got {actual_value}")


    @pytest.mark.parametrize("doc", filtered_docs)
    def test_all_containers_have_security_context(self, doc):
        """Test to ensure all containers have a securityContext defined."""

        pod_spec = get_pod_spec_from_doc(doc)
        containers = pod_spec.get("containers", [])
        init_containers = pod_spec.get("initContainers", [])
        all_containers = containers + init_containers

        doc_name = doc.get("metadata", {}).get("name", "unknown")
        doc_kind = doc.get("kind")

        assert all_containers, f"No containers found in {doc_kind}/{doc_name}"

        for i, container in enumerate(all_containers):
            container_name = container.get("name", f"container-{i}")
            container_security_context = container.get("securityContext")

            assert container_security_context is not None, f"Container '{container_name}' in {doc_kind}/{doc_name} must have a securityContext"

            assert container_security_context, f"Container '{container_name}' in {doc_kind}/{doc_name} has empty securityContext"

    @pytest.mark.parametrize("doc", job_docs)
    def test_job_template_structure(self, doc):
        """Test that Job and CronJob templates have the correct structure for security contexts."""

        doc_name = doc.get("metadata", {}).get("name", "unknown")
        doc_kind = doc.get("kind")

        if doc_kind == "Job":
            # Job: spec.template.spec
            template_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
            assert template_spec, f"Job {doc_name} missing spec.template.spec"

        elif doc_kind == "CronJob":
            # CronJob: spec.jobTemplate.spec.template.spec
            job_template = doc.get("spec", {}).get("jobTemplate", {})
            assert job_template, f"CronJob {doc_name} missing spec.jobTemplate"

            template_spec = job_template.get("spec", {}).get("template", {}).get("spec", {})
            assert template_spec, f"CronJob {doc_name} missing spec.jobTemplate.spec.template.spec"

        security_context = template_spec.get("securityContext")
        assert security_context is not None, f"{doc_kind} {doc_name} missing securityContext in template spec"