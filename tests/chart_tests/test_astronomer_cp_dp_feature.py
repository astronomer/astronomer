import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


PLANE_COMPONENT_MAP = {
    "controlplane": ["houston", "nginx", "astro-ui", "elasticsearch", "registry", "prometheus", "fluentd", "config-syncer"],
    "dataplane": ["nginx", "commander", "prometheus"],
}


def filter_docs_by_component(docs, component):
    """Filter templates by component name."""
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
        cp_resources = filter_docs_by_component(docs, "controlplane")
        assert len(cp_resources) > 0

        dp_resources = filter_docs_by_component(docs, "dataplane")
        assert len(dp_resources) == 0

        cp_components = PLANE_COMPONENT_MAP["controlplane"]
        component_names = [get_component_name(doc) for doc in docs]

        for component in cp_components:
            assert component in component_names, f"CP component '{component}' not found when only CP is enabled"

    def test_astronomer_dp_only(self, kube_version):
        """Test that helm renders the correct templates when only the dataplane is enabled."""
        
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": False}, "dataplane": {"enabled": True}}},
        )
        cp_resources = filter_docs_by_component(docs, "controlplane")
        assert len(cp_resources) == 0

        dp_resources = filter_docs_by_component(docs, "dataplane")
        assert len(dp_resources) > 0

        dp_components = PLANE_COMPONENT_MAP["dataplane"]
        component_names = [get_component_name(doc) for doc in docs]

        for component in dp_components:
            assert component in component_names, f"DP component '{component}' not found when only DP is enabled"

    def test_astronomer_both_cp_dp_enabled(self, kube_version):
        """Test when both Controlplane and Dataplane features are enabled."""
        
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": True}, "dataplane": {"enabled": True}}},
        )
        cp_resources = filter_docs_by_component(docs, "controlplane")
        assert len(cp_resources) > 0

        dp_resources = filter_docs_by_component(docs, "dataplane")
        assert len(dp_resources) > 0

    def test_astronomer_both_cp_dp_disabled(self, kube_version):
        """Test when both CP and DP features are disabled."""
        
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": False}, "dataplane": {"enabled": False}}},
        )
        cp_resources = filter_docs_by_component(docs, "controlplane")
        assert len(cp_resources) == 0

        dp_resources = filter_docs_by_component(docs, "dataplane")
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
            chart_identifier = create_doc_identifier(chart)

            found_in_plane = False
            actual_plane = chart.get("metadata", {}).get("labels", {}).get("plane")

            for plane, components in PLANE_COMPONENT_MAP.items():
                if component_name in components:
                    if plane == actual_plane:
                        found_in_plane = True
                        break

            if any(component_name in components for plane, components in PLANE_COMPONENT_MAP.items()):
                assert found_in_plane, (
                    f"Component '{component_name}' ({chart_identifier}) has plane label '{actual_plane}' "
                    f"but is not listed in that plane in PLANE_COMPONENT_MAP"
                )

    def test_no_components_with_incorrect_plane_labels(self, kube_version):
        """Test that there are no components with plane labels that don't match the component map."""
        
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": True}, "dataplane": {"enabled": True}}},
        )

        cp_resources = filter_docs_by_component(docs, "controlplane")
        assert len(cp_resources) > 0
        dp_resources = filter_docs_by_component(docs, "dataplane")
        assert len(dp_resources) > 0

        labeled_resources = [
            doc
            for doc in docs
            if doc.get("metadata", {}).get("labels", {}).get("component") and doc.get("metadata", {}).get("labels", {}).get("plane")
        ]

        for resource in labeled_resources:
            component = resource.get("metadata", {}).get("labels", {}).get("component")
            actual_plane = resource.get("metadata", {}).get("labels", {}).get("plane")
            chart_identifier = create_doc_identifier(resource)

            if not any(component in components for components in PLANE_COMPONENT_MAP.values()):
                continue

            assert component in PLANE_COMPONENT_MAP.get(actual_plane, []), (
                f"Resource {chart_identifier} (component: {component}) has plane label '{actual_plane}' "
                f"but is not listed in that plane in PLANE_COMPONENT_MAP"
            )

    def test_multi_plane_components_behavior(self, kube_version):
        """Test that components appear in the correct planes based on which features are enabled."""

        multi_plane_components = set()
        for plane, components in PLANE_COMPONENT_MAP.items():
            for component in components:
                for other_plane, other_components in PLANE_COMPONENT_MAP.items():
                    if plane != other_plane and component in other_components:
                        multi_plane_components.add(component)

        cp_only_docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": True}, "dataplane": {"enabled": False}}},
        )

        cp_only_component_names = [get_component_name(doc) for doc in cp_only_docs]

        for component in PLANE_COMPONENT_MAP["controlplane"]:
            assert component in cp_only_component_names, f"CP component '{component}' not found when only CP is enabled"

        dp_only_components = [
            component for component in PLANE_COMPONENT_MAP["dataplane"] 
            if component not in PLANE_COMPONENT_MAP["controlplane"]
        ]
        for component in dp_only_components:
            assert component not in cp_only_component_names, f"DP-only component '{component}' found when only CP is enabled"

        dp_only_docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": False}, "dataplane": {"enabled": True}}},
        )

        dp_only_component_names = [get_component_name(doc) for doc in dp_only_docs]

        for component in PLANE_COMPONENT_MAP["dataplane"]:
            assert component in dp_only_component_names, f"DP component '{component}' not found when only DP is enabled"
        cp_only_components = [
            component for component in PLANE_COMPONENT_MAP["controlplane"] 
            if component not in PLANE_COMPONENT_MAP["dataplane"]
        ]
        for component in cp_only_components:
            assert component not in dp_only_component_names, f"CP-only component '{component}' found when only DP is enabled"
        both_enabled_docs = render_chart(
            kube_version=kube_version,
            values={"global": {"controlplane": {"enabled": True}, "dataplane": {"enabled": True}}},
        )
        for component in multi_plane_components:
            planes_with_component = [
                plane for plane, components in PLANE_COMPONENT_MAP.items()
                if component in components
            ]
            occurrences = sum(1 for doc in both_enabled_docs if get_component_name(doc) == component)

            expected_count = len(planes_with_component)
            assert occurrences == expected_count, (
                f"Component '{component}' should appear {expected_count} times "
                f"(once per plane) but appears {occurrences} times"
            )