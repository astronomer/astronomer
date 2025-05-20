import jmespath
import pytest

from tests.utils import get_all_features
from tests.utils.chart import render_chart


def init_test_pod_annotation_configs():
    chart_values = get_all_features()
    chart_values["global"]["podAnnotations"] = {"app.cloud.io": "astronomer"}

    kubernetes_objects = {
        "StatefulSet": "spec.template.metadata.annotations",
        "Deployment": "spec.template.metadata.annotations",
        "CronJob": "spec.jobTemplate.spec.template.metadata.annotations",
        "Job": "spec.template.metadata.annotations",
        "DaemonSet": "spec.template.metadata.annotations",
        "Pod": "metadata.annotations",
    }

    docs = render_chart(values=chart_values)

    pod_docs = []
    for key, val in kubernetes_objects.items():
        pod_docs += jmespath.search(
            f"[?kind == `{key}`].{{name: metadata.name, kind: kind, chart: metadata.labels.chart, annotations: {val}}}",
            docs,
        )

    return {f"{doc['chart']}_{doc['kind']}_{doc['name']}": doc["annotations"] for doc in pod_docs}


test_pod_annotations_configs_data = init_test_pod_annotation_configs()


@pytest.mark.parametrize(
    "pod_annotations",
    test_pod_annotations_configs_data.values(),
    ids=test_pod_annotations_configs_data.keys(),
)
def test_pod_labels_configs(pod_annotations):
    """Annotations check for definition."""
    assert "astronomer" == pod_annotations["app.cloud.io"]
