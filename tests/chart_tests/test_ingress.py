from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import json


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
        )

        assert len(docs) == 1

        doc = docs[0]

        assert len(doc["metadata"]["annotations"]) >= 4

        doc["spec"]["rules"] == json.loads(
            """
        [{"host":"example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}},
        {"host":"app.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}},
        {"host":"registry.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"release-name-registry","port":{"name":"registry-http"}}}}]}}]
        """
        )

    def test_astro_ui_per_host_ingress(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"enablePerHostIngress": True}},
            show_only=[
                "charts/astronomer/templates/astro-ui/astro-ui-ingress.yaml",
                "charts/astronomer/templates/ingress.yaml",
            ],
        )
        assert len(docs) == 2
        assert docs[0]["spec"]["rules"] == json.loads(
            """
        [
            {"host":"app.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}}
        ]
        """
        )
        assert docs[1]["spec"]["rules"] == json.loads(
            """
        [
            {"host":"example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}}
        ]
        """
        )

    def test_registry_per_host_ingress(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"enablePerHostIngress": True}},
            show_only=[
                "charts/astronomer/templates/registry/registry-ingress.yaml",
                "charts/astronomer/templates/ingress.yaml",
            ],
        )
        assert len(docs) == 1
        expected_rules_v1 = json.loads(
            """
        [
        {"host":"registry.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"release-name-registry","port":{"name":"registry-http"}}}}]}}]
        """
        )
        assert docs[0]["spec"]["rules"] == expected_rules_v1

    def test_single_ingress_per_host(self, kube_version):
        default_docs = render_chart(values={"global": {"enablePerHostIngress": True}})
        ingresses = [
            doc for doc in default_docs if doc["kind"].lower() == "Ingress".lower()
        ]
        assert len(ingresses) == 9
        assert all(len(doc["spec"]["rules"]) == 1 for doc in ingresses)
        assert all(len(doc["spec"]["tls"][0]["hosts"]) == 1 for doc in ingresses)
        assert all(doc["apiVersion"] == "networking.k8s.io/v1" for doc in ingresses)
        assert all(doc["kind"] == "Ingress" for doc in ingresses)
        assert all(
            doc["metadata"]["annotations"]["kubernetes.io/ingress.class"]
            == "release-name-nginx"
            for doc in ingresses
        )
        assert all(
            doc["metadata"]["annotations"]["kubernetes.io/tls-acme"] == "false"
            for doc in ingresses
        )
