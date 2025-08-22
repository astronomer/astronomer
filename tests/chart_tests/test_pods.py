import pytest

from tests.utils import get_all_features, get_pod_template
from tests.utils.chart import render_chart


class TestPodLabelsDefault:
    """Test that all pods have all expected labels by default."""

    @staticmethod
    def init_test_pod_labels_configs():
        chart_values = get_all_features()

        docs = render_chart(values=chart_values)

        pod_docs = [
            {
                "chart": doc.get("metadata", {}).get("labels", {}).get("chart"),
                "kind": doc.get("kind"),
                "labels": doc.get("metadata", {}).get("labels", {}),
                "name": doc.get("metadata", {}).get("name"),
            }
            for doc in [y for y in [get_pod_template(x) for x in docs] if y]
        ]

        return {f"{doc['chart']}_{doc['kind']}_{doc['name']}": doc["labels"] for doc in pod_docs}

    test_pod_labels_configs_data = init_test_pod_labels_configs()

    @pytest.mark.parametrize(
        "pod_labels",
        test_pod_labels_configs_data.values(),
        ids=test_pod_labels_configs_data.keys(),
    )
    def test_pod_labels_configs(self, pod_labels):
        """Labels check for definition."""
        assert pod_labels is not None
        assert "app" in pod_labels
        assert "version" in pod_labels
        assert "tier" in pod_labels
        assert "component" in pod_labels
        assert "release" in pod_labels


class TestPodLabelsCustom:
    """Test that we can define one configuration setting to get labels on all pod objects."""

    values = {"global": {"podLabels": {"life-outlook": "sunshine-and-rainbows"}}}
    docs = render_chart(values=values)
    pod_templates = [x for x in [get_pod_template(doc) for doc in docs] if x]

    pod_template_labels = [x.get("metadata", {}).get("labels", {}) for x in pod_templates]

    @pytest.mark.parametrize(
        "template",
        pod_template_labels,
        ids=[f"{doc.get('app', 'unknown')}" for doc in pod_template_labels],
    )
    def test_global_pod_labels(self, template):
        assert template.get("life-outlook", "") == "sunshine-and-rainbows", f"Expected 'life-outlook' label in {template}"
