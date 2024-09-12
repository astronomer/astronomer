from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions, get_containers_by_name


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestFluentdConfig:
    show_only = ["charts/fluentd/templates/fluentd-daemonset.yaml"]

    def test_fluentd_daemonset(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
        )
        # assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        # print (c_by_name)
        assert c_by_name["fluentd"]["name"] == "fluentd"
        liveness_probe = c_by_name["fluentd"]["livenessProbe"]
        assert liveness_probe["failureThreshold"] == 3
        assert liveness_probe["initialDelaySeconds"] == 30
        assert liveness_probe["periodSeconds"] == 15
        assert liveness_probe["successThreshold"] == 1
        assert liveness_probe["timeoutSeconds"] == 5
