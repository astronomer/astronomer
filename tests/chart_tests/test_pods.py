import pytest

from tests.utils import get_all_features, get_pod_template
from tests.utils.chart import render_chart


class TestPodLabelsDefault:
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
