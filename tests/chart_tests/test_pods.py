import jmespath
import pytest

import tests.chart_tests as chart_tests
from tests.chart_tests.helm_template_generator import render_chart


def init_test_pod_labels_configs():
    chart_values = chart_tests.get_all_features()

    kubernetes_objects = {
        "StatefulSet": "spec.template.metadata.labels",
        "Deployment": "spec.template.metadata.labels",
        "CronJob": "spec.jobTemplate.spec.template.metadata.labels",
        "Job": "spec.template.metadata.labels",
        "DaemonSet": "spec.template.metadata.labels",
        "Pod": "metadata.labels",
    }

    docs = render_chart(values=chart_values)

    pod_docs = []
    for key, val in kubernetes_objects.items():
        pod_docs += jmespath.search(
            "[?kind == `%s`].{name: metadata.name, kind: kind, chart: metadata.labels.chart, labels: %s}"
            % (key, val),
            docs,
        )

    return {
        f'{doc["chart"]}_{doc["kind"]}_{doc["name"]}': doc["labels"] for doc in pod_docs
    }


test_pod_labels_configs_data = init_test_pod_labels_configs()


@pytest.mark.parametrize(
    "pod_labels",
    test_pod_labels_configs_data.values(),
    ids=test_pod_labels_configs_data.keys(),
)
def test_pod_labels_configs(pod_labels):
    """Labels check for definition."""
    assert pod_labels is not None
    assert "app" in pod_labels
    assert "version" in pod_labels
    assert "tier" in pod_labels
    assert "component" in pod_labels
    assert "release" in pod_labels
