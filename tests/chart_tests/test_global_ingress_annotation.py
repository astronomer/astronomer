import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestGlobabIngressAnnotation:
    def test_global_ingress_with_astronomer_ingress(self, kube_version):
        """Test global ingress annotation for platform ingress."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"extraAnnotations": {"route.openshift.io/termination": "passthrough"}}},
            show_only=[
                "charts/alertmanager/templates/ingress.yaml",
                "charts/grafana/templates/ingress.yaml",
                "charts/kibana/templates/ingress.yaml",
                "charts/prometheus/templates/ingress.yaml",
                "charts/astronomer/templates/ingress.yaml",
                "charts/astronomer/templates/registry/registry-ingress.yaml",
            ],
        )

        assert len(docs) == 5
        for doc in docs:
            assert doc["kind"] == "Ingress"
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert "passthrough" in doc["metadata"]["annotations"]["route.openshift.io/termination"]
            assert len(doc["metadata"]["annotations"]) >= 4
