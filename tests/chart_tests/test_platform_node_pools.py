import jmespath
import pytest

from tests.utils import get_all_features
from tests.utils.chart import render_chart

ignore_list = ["postgresql", "cert-copy", "cert-copy-and-toml-update"]


def init_test_pod_spec():
    """initialize with all default features and returns pod spec"""
    chart_values = get_all_features()

    kubernetes_objects = {
        "StatefulSet": "spec.template.spec",
        "Deployment": "spec.template.spec",
        "DaemonSet": "spec.template.spec",
        "CronJob": "spec.jobTemplate.spec.template.spec",
        "Job": "spec.template.spec",
        "Pod": "spec",
    }

    docs = render_chart(values=chart_values)

    pod_docs = []
    for key, val in kubernetes_objects.items():
        pod_docs += jmespath.search(
            f"[?kind == `{key}`].{{name: metadata.name, chart: metadata.labels.chart, kind: kind, spec: {val}}}",
            docs,
        )

    return {f"{doc['chart']}_{doc['kind']}_{doc['name']}": doc["spec"] for doc in pod_docs}


test_pod_resources_configs_data = init_test_pod_spec()


class TestPodResources:
    @pytest.mark.parametrize(
        "pod_spec",
        test_pod_resources_configs_data.values(),
        ids=test_pod_resources_configs_data.keys(),
    )
    def test_pod_resources_configs(self, pod_spec):
        """Test that all pod spec have a nodeSelector,affinity and tolerations section defined."""
        if pod_spec["containers"][0]["name"].split("release-name-")[-1] in ignore_list:
            pytest.skip("Info: Resource doesn't adopt global nodepool" + pod_spec["containers"][0]["name"])
        else:
            assert "nodeSelector" in pod_spec
            assert "affinity" in pod_spec
            assert "tolerations" in pod_spec
