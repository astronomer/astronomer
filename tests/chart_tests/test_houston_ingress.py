import jmespath
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
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
            values={"global": {"baseDomain": "test.local"}}
        )

        assert len(docs) == 1

        doc = docs[0]

        annotations = jmespath.search("metadata.annotations", doc)
        assert "kubernetes.io/ingress.class" not in annotations

        ingress_class_name = jmespath.search("spec.ingressClassName", doc)
        assert ingress_class_name == "release-name-nginx"

        assert len(annotations) > 1

        _, minor, _ = (int(x) for x in kube_version.split("."))

        if minor >= 19:
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert "release-name-houston" in [
                name[0] for name in jmespath.search("spec.rules[*].http.paths[*].backend.service.name", doc)
            ]
            assert "houston-http" in [
                port[0] for port in jmespath.search("spec.rules[*].http.paths[*].backend.service.port.name", doc)
            ]

        if minor < 19:
            assert doc["apiVersion"] == "networking.k8s.io/v1beta1"
            assert "release-name-houston" in [
                name[0] for name in jmespath.search("spec.rules[*].http.paths[*].backend.serviceName", doc)
            ]
            assert "houston-http" in [port[0] for port in jmespath.search("spec.rules[*].http.paths[*].backend.servicePort", doc)]

    def test_protect_houston_internal_urls(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
            values={"global": {"baseDomain": "test.local"}}
        )
        assert len(docs) == 1
        doc = docs[0]

        # Verify IngressClass is used instead of deprecated annotation
        ingress_class_name = jmespath.search("spec.ingressClassName", doc)
        assert ingress_class_name == "release-name-nginx"

        # Test the security configuration snippet
        annotations = jmespath.search("metadata.annotations", doc)
        assert (
            annotations["nginx.ingress.kubernetes.io/configuration-snippet"]
            == r"""location ~ ^/v1/(registry\/events|alerts|elasticsearch|metrics) {
  deny all;
  return 403;
}
"""
        )

    def test_houston_ingress_overrides(self, kube_version):
        custom_annotations = {
            "nginx.ingress.kubernetes.io/upstream-keepalive-connections": "9999",
            "nginx.ingress.kubernetes.io/upstream-keepalive-timeout": "7777",
        }
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"baseDomain": "test.local"},
                "astronomer": {"houston": {"ingress": {"annotation": custom_annotations}}}
            },
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]

        ingress_class_name = jmespath.search("spec.ingressClassName", doc)
        assert ingress_class_name == "release-name-nginx"

        annotations = jmespath.search("metadata.annotations", doc)
        assert "kubernetes.io/ingress.class" not in annotations

        assert annotations["nginx.ingress.kubernetes.io/upstream-keepalive-connections"] == "9999"
        assert annotations["nginx.ingress.kubernetes.io/upstream-keepalive-timeout"] == "7777"

    def test_houston_ingress_with_auth_sidecar(self, kube_version):
        """Test that when authSidecar is enabled, no auth annotations are added"""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
            values={
                "global": {
                    "baseDomain": "test.local",
                    "authSidecar": {"enabled": True}
                }
            }
        )
        assert len(docs) == 1
        doc = docs[0]

        ingress_class_name = jmespath.search("spec.ingressClassName", doc)
        assert ingress_class_name == "release-name-nginx"

        annotations = jmespath.search("metadata.annotations", doc) or {}
        assert "kubernetes.io/ingress.class" not in annotations
        assert "nginx.ingress.kubernetes.io/configuration-snippet" not in annotations
        assert "nginx.ingress.kubernetes.io/proxy-buffer-size" not in annotations

    def test_houston_ingress_custom_class_name(self, kube_version):
        """Test using a custom IngressClass name"""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
            values={
                "global": {
                    "baseDomain": "test.local",
                    "ingress": {"className": "custom-nginx"}
                }
            }
        )
        assert len(docs) == 1
        doc = docs[0]

        ingress_class_name = jmespath.search("spec.ingressClassName", doc)
        assert ingress_class_name == "custom-nginx"

        annotations = jmespath.search("metadata.annotations", doc)
        assert "kubernetes.io/ingress.class" not in annotations