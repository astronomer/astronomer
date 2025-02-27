from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonBootstrapServiceAccount:
    def test_houston_bootstrap_serviceaccount_defaults(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/api/houston-bootstrap-serviceaccount.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "ServiceAccount"
        assert "annotations" in doc["metadata"]
