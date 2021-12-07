from tests.helm_template_generator import render_chart
import jmespath
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestIngress:
    def test_prometheus_ingress(self, kube_version):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/prometheus/templates/ingress.yaml"],
        )

        assert len(docs) == 1

        doc = docs[0]

        annotations = jmespath.search("metadata.annotations", doc)
        assert len(annotations) > 1
        assert annotations["kubernetes.io/ingress.class"] == "RELEASE-NAME-nginx"

        _, minor, _ = (int(x) for x in kube_version.split("."))

        if minor >= 19:
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert "RELEASE-NAME-prometheus" in [
                name[0]
                for name in jmespath.search(
                    "spec.rules[*].http.paths[*].backend.service.name", doc
                )
            ]
            assert "prometheus-data" in [
                port[0]
                for port in jmespath.search(
                    "spec.rules[*].http.paths[*].backend.service.port.name", doc
                )
            ]

        if minor < 19:
            assert doc["apiVersion"] == "networking.k8s.io/v1beta1"
            assert "RELEASE-NAME-prometheus" in [
                name[0]
                for name in jmespath.search(
                    "spec.rules[*].http.paths[*].backend.serviceName", doc
                )
            ]
            assert "prometheus-data" in [
                port[0]
                for port in jmespath.search(
                    "spec.rules[*].http.paths[*].backend.servicePort", doc
                )
            ]
