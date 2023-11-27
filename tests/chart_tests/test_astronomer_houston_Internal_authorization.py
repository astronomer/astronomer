import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonInternalAuthorization:
    def test_ingress_with_authorization_defaults(self, kube_version):
        """Test Alertmanager Service with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/alertmanager/templates/ingress.yaml",
                "charts/grafana/templates/ingress.yaml",
                "charts/kibana/templates/ingress.yaml",
                "charts/prometheus/templates/ingress.yaml",
            ],
        )

        assert len(docs) == 4
        for doc in docs:
            assert doc["kind"] == "Ingress"
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert (
                "https://houston.example.com/v1/authorization"
                in doc["metadata"]["annotations"][
                    "nginx.ingress.kubernetes.io/auth-url"
                ]
            )

    def test_ingress_with_internal_authorization(self, kube_version):
        """Test Alertmanager Service with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"enableHoustonInternalAuthorization": True}},
            show_only=[
                "charts/alertmanager/templates/ingress.yaml",
                "charts/grafana/templates/ingress.yaml",
                "charts/kibana/templates/ingress.yaml",
                "charts/prometheus/templates/ingress.yaml",
            ],
        )

        assert len(docs) == 4
        for doc in docs:
            assert doc["kind"] == "Ingress"
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert (
                "http://release-name-houston.default.svc.cluster.local:8871/v1/authorization"
                in doc["metadata"]["annotations"][
                    "nginx.ingress.kubernetes.io/auth-url"
                ]
            )
