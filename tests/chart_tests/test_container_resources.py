import jmespath
import pytest

import tests.chart_tests as chart_tests
from tests.chart_tests.helm_template_generator import render_chart


def init_test_pod_resources():
    chart_values = chart_tests.get_all_features()

    kubernetes_objects = {
        "StatefulSet": "spec.template.spec.containers",
        "Deployment": "spec.template.spec.containers",
        "CronJob": "spec.jobTemplate.spec.template.spec.containers",
        "Job": "spec.template.spec.containers",
        "DaemonSet": "spec.template.spec.containers",
        "Pod": "spec.containers",
    }

    docs = render_chart(values=chart_values)

    pod_docs = []
    for key, val in kubernetes_objects.items():
        pod_docs += jmespath.search(
            f"[?kind == `{key}`].{{name: metadata.name, chart: metadata.labels.chart, kind: kind, container: {val}}}",
            docs,
        )

    return {f'{doc["chart"]}_{doc["kind"]}_{doc["name"]}': doc["container"] for doc in pod_docs}


test_pod_resources_configs_data = init_test_pod_resources()


class TestPodResources:
    @pytest.mark.parametrize(
        "pod_resources",
        test_pod_resources_configs_data.values(),
        ids=test_pod_resources_configs_data.keys(),
    )
    def test_pod_resources_configs(self, pod_resources):
        """Test that all pod containers have a resources section defined."""
        for container in pod_resources:
            assert "resources" in container
