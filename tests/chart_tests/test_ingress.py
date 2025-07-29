import json

import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestIngress:
    def test_basic_ingress(self, kube_version):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/ingress.yaml"],
            values={"global": {"baseDomain": "example.com"}}
        )

        assert len(docs) == 1

        doc = docs[0]

        ingress_class_name = doc["spec"]["ingressClassName"]
        assert ingress_class_name == "release-name-nginx"

        annotations = doc["metadata"]["annotations"]
        assert "kubernetes.io/ingress.class" not in annotations

        assert len(annotations) >= 1

        assert doc["spec"]["rules"] == json.loads(
            """
            [{"host":"example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":
            "release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}},{"host":"app.example.com","http":{"paths":[{"path":"/",
            "pathType":"Prefix","backend":{"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}},{"host":
            "registry.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":
            "release-name-registry","port":{"name":"registry-http"}}}}]}}]
            """
        )

    def test_astro_ui_per_host_ingress(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "enablePerHostIngress": True,
                    "baseDomain": "example.com"
                }
            },
            show_only=[
                "charts/astronomer/templates/astro-ui/astro-ui-ingress.yaml",
                "charts/astronomer/templates/ingress.yaml",
            ],
        )
        assert len(docs) == 2

        for doc in docs:
            assert doc["spec"]["ingressClassName"] == "release-name-nginx"
            assert "kubernetes.io/ingress.class" not in doc["metadata"]["annotations"]

        assert docs[0]["spec"]["rules"] == json.loads(
            """
            [{"host":"app.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":
            {"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}}]
            """
        )
        assert docs[1]["spec"]["rules"] == json.loads(
            """
            [{"host":"example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":
            {"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}}]
            """
        )

    def test_registry_per_host_ingress(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "enablePerHostIngress": True,
                    "baseDomain": "example.com"
                }
            },
            show_only=[
                "charts/astronomer/templates/registry/registry-ingress.yaml",
                "charts/astronomer/templates/ingress.yaml",
            ],
        )
        assert len(docs) == 1

        assert docs[0]["spec"]["ingressClassName"] == "release-name-nginx"
        assert "kubernetes.io/ingress.class" not in docs[0]["metadata"]["annotations"]

        expected_rules_v1 = json.loads(
            """
            [{"host":"registry.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":
            {"service":{"name":"release-name-registry","port":{"name":"registry-http"}}}}]}}]
            """
        )
        assert docs[0]["spec"]["rules"] == expected_rules_v1

    def test_single_ingress_per_host(self, kube_version):
        default_docs = render_chart(
            values={
                "global": {
                    "enablePerHostIngress": True,
                    "baseDomain": "example.com"
                }
            }
        )
        ingresses = [doc for doc in default_docs if doc["kind"].lower() == "Ingress".lower()]
        assert len(ingresses) == 8
        assert all(len(doc["spec"]["rules"]) == 1 for doc in ingresses)
        assert all(len(doc["spec"]["tls"][0]["hosts"]) == 1 for doc in ingresses)
        assert all(doc["apiVersion"] == "networking.k8s.io/v1" for doc in ingresses)
        assert all(doc["kind"] == "Ingress" for doc in ingresses)

        assert all(doc["spec"]["ingressClassName"] == "release-name-nginx" for doc in ingresses)
        assert all("kubernetes.io/ingress.class" not in doc["metadata"]["annotations"] for doc in ingresses)

    def test_kibana_custom_ingress_annotation(self, kube_version):
        """validate kibana to add custom ingress annotation to ingress objects"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"baseDomain": "example.com"},
                "kibana": {"ingressAnnotations": {"kubernetes.io/software-enable": "enabled"}}
            },
            show_only=[
                "charts/kibana/templates/ingress.yaml",
            ],
        )
        assert len(docs) == 1

        assert docs[0]["spec"]["ingressClassName"] == "release-name-nginx"
        assert "kubernetes.io/ingress.class" not in docs[0]["metadata"]["annotations"]

        assert docs[0]["metadata"]["annotations"]["kubernetes.io/software-enable"] == "enabled"

    def test_prometheus_federate_ingress(self, kube_version):
        """Test prometheus federate ingress configuration"""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/prometheus/templates/ingress.yaml", "charts/prometheus/templates/prometheus-federate-ingress.yaml"],
            values={"global": {"baseDomain": "example.com"}},
        )

        assert len(docs) == 2

        federate_ingress = next((doc for doc in docs if "federate-ingress" in doc["metadata"]["name"]), None)
        assert federate_ingress is not None

        assert federate_ingress["kind"] == "Ingress"
        assert federate_ingress["apiVersion"] == "networking.k8s.io/v1"

        assert federate_ingress["spec"]["ingressClassName"] == "release-name-nginx"

        annotations = federate_ingress["metadata"]["annotations"]
        assert "kubernetes.io/ingress.class" not in annotations

        auth_annotations = ["nginx.ingress.kubernetes.io/auth-signin", "nginx.ingress.kubernetes.io/auth-response-headers"]
        for auth_annotation in auth_annotations:
            assert auth_annotation not in annotations

        rules = federate_ingress["spec"]["rules"]
        assert len(rules) == 1
        paths = rules[0]["http"]["paths"]
        assert len(paths) == 1
        assert paths[0]["path"] == "/federate"
        assert paths[0]["pathType"] == "Exact"

        backend = paths[0]["backend"]
        assert backend["service"]["port"]["name"] == "prometheus-data"

    def test_ingress_custom_class_name(self, kube_version):
        """Test using custom IngressClass name"""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/ingress.yaml"],
            values={
                "global": {
                    "baseDomain": "example.com",
                    "ingress": {"className": "custom-nginx"}
                }
            }
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["spec"]["ingressClassName"] == "custom-nginx"
        assert "kubernetes.io/ingress.class" not in doc["metadata"]["annotations"]

    def test_ingress_with_auth_sidecar(self, kube_version):
        """Test ingress behavior when authSidecar is enabled"""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/ingress.yaml"],
            values={
                "global": {
                    "baseDomain": "example.com",
                    "authSidecar": {"enabled": True}
                }
            }
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["spec"]["ingressClassName"] == "release-name-nginx"

        annotations = doc["metadata"]["annotations"] or {}
        assert "kubernetes.io/ingress.class" not in annotations
        nginx_config_annotations = [
            "nginx.ingress.kubernetes.io/custom-http-errors",
            "nginx.ingress.kubernetes.io/configuration-snippet"
        ]
        for annotation in nginx_config_annotations:
            assert annotation not in annotations