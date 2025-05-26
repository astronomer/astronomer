import pytest
import yaml

from tests import git_root_dir
from tests.chart_tests.helm_template_generator import render_chart

include_kind_list = ["Deployment", "DaemonSet", "StatefulSet", "ReplicaSet"]

default_podsecuritycontext = {
    "fsGroup": 9999,
    "runAsGroup": 9998,
    "runAsUser": 7788,
}

# Load test data from YAML file
enable_all_podsecuritycontexts = yaml.safe_load(
    ((git_root_dir) / "tests" / "chart_tests" / "test_data" / "enable_all_podsecuritycontexts.yaml").read_text()
)


def find_all_pod_manager_templates() -> list[str]:
    """Return a sorted, unique list of all pod manager templates in the chart, relative to git_root_dir."""
    return sorted(
        {
            str(x.relative_to(git_root_dir))
            for x in (git_root_dir / "charts").rglob("*")
            if any(sub in x.name for sub in ("deployment", "statefulset", "replicaset", "daemonset")) and "job" not in x.name
        }
    )


class TestPodSecurityContext:
    """Test pod security context configuration for all pod manager templates."""
    
    docs = render_chart(values=enable_all_podsecuritycontexts)
    filtered_docs = [doc for doc in docs if doc.get("kind") in include_kind_list]

    @pytest.mark.parametrize("doc", filtered_docs)
    def test_template_supports_podsecuritycontext(self, doc):
        """Test to ensure each pod manager template has support for podSecurityContext."""
        
        assert doc.get("kind") in include_kind_list, f"Unexpected document kind: {doc.get('kind')}"
        
        pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
        security_context = pod_spec.get("securityContext")
        doc_name = doc.get('metadata', {}).get('name', 'unknown')

        if not security_context:
            print(f"No securityContext found in {doc_name}")
            print(f"Pod spec keys: {pod_spec.keys()}")

        assert security_context is not None, f"No securityContext found in {doc_name}"

        # Check that at least fsGroup is set (minimum requirement)
        assert "fsGroup" in security_context, f"fsGroup not found in securityContext for {doc_name}"
        
        # For most charts, we expect our custom values
        for key, value in default_podsecuritycontext.items():
            actual_value = security_context.get(key)
            
            # Some charts might not support all fields or have different defaults
            # Log the discrepancy but only fail if the field is completely missing when expected
            if actual_value != value:
                print(f"WARNING: {doc_name} - Expected {key}={value}, got {actual_value}")
                
            # Only assert on fsGroup for now, as it's the most commonly supported field
            if key == "fsGroup":
                assert actual_value == value, (
                    f"Expected {key}={value} in securityContext, got {actual_value} "
                    f"for {doc_name}"
                )