from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import jmespath


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAuthSidecar:
    def test_authSidecar_alertmanager(self, kube_version):
        """Test Alertmanager Service with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"authSidecar": {"enabled": True}}},
            show_only=[
                "charts/alertmanager/templates/alertmanager-statefulset.yaml",
                "charts/alertmanager/templates/alertmanager-auth-sidecar-configmap.yaml",
                "charts/alertmanager/templates/alertmanager-service.yaml",
                "charts/alertmanager/templates/alertmanager-networkpolicy.yaml",
                "charts/alertmanager/templates/ingress.yaml",
            ],
        )

        assert len(docs) == 5
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-alertmanager"
        assert "auth-proxy" == doc["spec"]["template"]["spec"]["containers"][1]["name"]

        assert "Service" == jmespath.search("kind", docs[2])
        assert "RELEASE-NAME-alertmanager" == jmespath.search("metadata.name", docs[2])
        assert "ClusterIP" == jmespath.search("spec.type", docs[2])
        assert {
            "name": "auth-proxy",
            "protocol": "TCP",
            "port": 8084,
        } in jmespath.search("spec.ports", docs[2])

    def test_authSidecar_prometheus(self, kube_version):
        """Test Prometheus Service with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"authSidecar": {"enabled": True}}},
            show_only=[
                "charts/prometheus/templates/prometheus-statefulset.yaml",
                "charts/prometheus/templates/prometheus-auth-sidecar-configmap.yaml",
                "charts/prometheus/templates/prometheus-service.yaml",
                "charts/prometheus/templates/prometheus-networkpolicy.yaml",
                "charts/prometheus/templates/ingress.yaml",
            ],
        )

        assert len(docs) == 5
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-prometheus"
        assert "auth-proxy" == doc["spec"]["template"]["spec"]["containers"][0]["name"]

        assert "Service" == jmespath.search("kind", docs[2])
        assert "RELEASE-NAME-prometheus" == jmespath.search("metadata.name", docs[2])
        assert "ClusterIP" == jmespath.search("spec.type", docs[2])
        assert {
            "name": "auth-proxy",
            "protocol": "TCP",
            "port": 8084,
        } in jmespath.search("spec.ports", docs[2])

    def test_authSidecar_kibana(self, kube_version):
        """Test Kibana Service with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"authSidecar": {"enabled": True}}},
            show_only=[
                "charts/kibana/templates/kibana-deployment.yaml",
                "charts/kibana/templates/kibana-auth-sidecar-configmap.yaml",
                "charts/kibana/templates/kibana-service.yaml",
                "charts/kibana/templates/kibana-networkpolicy.yaml",
                "charts/kibana/templates/ingress.yaml",
            ],
        )

        assert len(docs) == 5
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-kibana"
        assert "auth-proxy" == doc["spec"]["template"]["spec"]["containers"][1]["name"]

        assert "Service" == jmespath.search("kind", docs[2])
        assert "RELEASE-NAME-kibana" == jmespath.search("metadata.name", docs[2])
        assert "ClusterIP" == jmespath.search("spec.type", docs[2])
        assert {
            "name": "auth-proxy",
            "protocol": "TCP",
            "port": 8084,
        } in jmespath.search("spec.ports", docs[2])
