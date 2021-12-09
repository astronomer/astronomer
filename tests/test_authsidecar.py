from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import jmespath
import yaml


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
        assert doc["spec"]["template"]["spec"]["containers"][1]["name"] == "auth-proxy"

        assert jmespath.search("kind", docs[2]) == "Service"
        assert jmespath.search("metadata.name", docs[2]) == "RELEASE-NAME-alertmanager"
        assert jmespath.search("spec.type", docs[2]) == "ClusterIP"
        assert {
            "name": "auth-proxy",
            "protocol": "TCP",
            "port": 8084,
        } in jmespath.search("spec.ports", docs[2])

        assert "NetworkPolicy" == docs[3]["kind"]
        assert [{"port": 8084, "protocol": "TCP"}] == jmespath.search(
            "spec.ingress[*].ports[1]", docs[3]
        )

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

        assert "NetworkPolicy" == docs[3]["kind"]
        assert [{"port": 8084, "protocol": "TCP"}] == jmespath.search(
            "spec.ingress[*].ports[1]", docs[3]
        )

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

        assert "NetworkPolicy" == docs[3]["kind"]
        assert [
            {
                "namespaceSelector": {
                    "matchLabels": {"network.openshift.io/policy-group": "ingress"}
                }
            }
        ] == jmespath.search("spec.ingress[0].from", docs[3])
        assert [{"port": 8084, "protocol": "TCP"}] == jmespath.search(
            "spec.ingress[*].ports[0]", docs[3]
        )

    def test_authSidecar_houston_configmap_without_annotation(self, kube_version):
        """Test Houston Configmap with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"authSidecar": {"enabled": True}}},
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        prod = yaml.safe_load(doc["data"]["production.yaml"])
        print(prod["deployments"]["authSideCar"])

        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-houston-config"

        expected_output = {
            "enabled": True,
            "repository": "nginxinc/nginx-unprivileged",
            "tag": "stable",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "annotations": {},
        }
        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_houston_configmap_with_annotation(self, kube_version):
        """Test Houston Configmap with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "authSidecar": {"enabled": True},
                    "extraAnnotations": {
                        "kubernetes.io/ingress.class": "astronomer-nginx",
                        "nginx.ingress.kubernetes.io/proxy-body-size": "1024m",
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-houston-config"

        expected_output = {
            "enabled": True,
            "repository": "nginxinc/nginx-unprivileged",
            "tag": "stable",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "annotations": {
                "kubernetes.io/ingress.class": "astronomer-nginx",
                "nginx.ingress.kubernetes.io/proxy-body-size": "1024m",
            },
        }
        assert expected_output == prod["deployments"]["authSideCar"]
