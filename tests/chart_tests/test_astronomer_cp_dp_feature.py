import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


COMPONENT_PLANE_MAP = {
    "astronomer-houston": "controlplane",
    "astronomer-nginx": "controlplane",
    "astronomer-astro-ui": "controlplane",
    "astronomer-elasticsearch": "controlplane",
    "astronomer-commander": "dataplane",
    "astronomer-registry": "dataplane",
    "astronomer-prometheus": "controlplane",
    "astronomer-prometheus": "dataplane"
}
def filter_docs_by_component(docs, component):
    return [doc for doc in docs if doc.get("metadata", {}).get("labels", {}).get("plane") == component]

def get_component_name(doc):
    """Extract component name from chart metadata."""
    return doc.get("metadata", {}).get("labels", {}).get("component")

def create_doc_identifier(doc):
    """Create a unique identifier for a k8s doc."""
    kind = doc.get("kind", "Unknown")
    name = doc.get("metadata", {}).get("name", "unnamed")
    namespace = doc.get("metadata", {}).get("namespace", "default")
    return f"{kind}/{namespace}/{name}"

@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerCpDpFeature:
    def test_astronomer_cp_only(self, kube_version):
        """Test that helm renders the correct templates when only the controlplane is enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": True}, "dataplane": {"enabled": False}}},
        )
        cp_resources = filter_charts_by_component(docs, "controlplane")
        assert len(cp_resources) > 0

        dp_resources = filter_charts_by_component(docs, "dataplane")
        assert len(dp_resources) == 0

    def test_astronomer_dp_only(self, kube_version):
        """Test that helm renders the correct templates when only the dataplane is enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": False}, "dataplane": {"enabled": True}}},
        )
        cp_resources = filter_charts_by_component(docs, "controlplane")
        assert len(cp_resources) == 0

        dp_resources = filter_charts_by_component(docs, "dataplane")
        assert len(dp_resources) > 0

    def test_astronomer_both_cp_dp_enabled(self, kube_version):
        """Test when both CP and DP features are enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": True}, "dataplane": {"enabled": True}}},
        )
        cp_resources = filter_charts_by_component(docs, "controlplane")
        assert len(cp_resources) > 0

        dp_resources = filter_charts_by_component(docs, "dataplane")
        assert len(dp_resources) > 0

    def test_astronomer_both_cp_dp_disabled(self, kube_version):
        """Test when both CP and DP features are disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": False}, "dataplane": {"enabled": False}}},
        )
        cp_resources = filter_charts_by_component(docs, "controlplane")
        assert len(cp_resources) == 0

        dp_resources = filter_charts_by_component(docs, "dataplane")
        assert len(dp_resources) == 0

    def test_components_have_correct_plane_labels(self, kube_version):
        """Test that all components have the correct plane labels according to the component map."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": True}, "dataplane": {"enabled": True}}},
        )
        component_charts = [doc for doc in docs if get_component_name(doc)]

        for chart in component_charts:
            component_name = get_component_name(chart)
            chart_identifier = get_chart_identifier(chart)

            if component_name not in COMPONENT_PLANE_MAP:
                continue
            expected_plane = COMPONENT_PLANE_MAP[component_name]
            actual_plane = chart.get("metadata", {}).get("labels", {}).get("plane")

            assert actual_plane == expected_plane, (
                f"Component '{component_name}' ({chart_identifier}) has incorrect plane label. "
                f"Expected: '{expected_plane}', Actual: '{actual_plane}'"
            )

    def test_no_components_with_incorrect_plane_labels(self, kube_version):
        """Test that there are no components with plane labels that don't match the component map."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": True}, "dataplane": {"enabled": True}}},
        )

        cp_resources = filter_charts_by_component(docs, "controlplane")
        assert len(cp_resources) > 0
        dp_resources = filter_charts_by_component(docs, "dataplane")
        assert len(dp_resources) > 0

        labeled_resources = [
            doc
            for doc in docs
            if doc.get("metadata", {}).get("labels", {}).get("component")
            and doc.get("metadata", {}).get("labels", {}).get("plane")
        ]

        for resource in labeled_resources:
            component = resource.get("metadata", {}).get("labels", {}).get("component")
            actual_plane = resource.get("metadata", {}).get("labels", {}).get("plane")
            chart_identifier = get_chart_identifier(resource)

            if component in COMPONENT_PLANE_MAP:
                expected_plane = COMPONENT_PLANE_MAP[component]
                assert actual_plane == expected_plane, (
                    f"Resource {chart_identifier} (component: {component}) has incorrect plane label. "
                    f"Expected: '{expected_plane}', Got: '{actual_plane}'"
                )
