import jmespath
import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


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
        assert annotations["kubernetes.io/ingress.class"] == "release-name-nginx"

        _, minor, _ = (int(x) for x in kube_version.split("."))

        if minor >= 19:
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert "release-name-prometheus" in [
                name[0] for name in jmespath.search("spec.rules[*].http.paths[*].backend.service.name", doc)
            ]
            assert "prometheus-data" in [
                port[0] for port in jmespath.search("spec.rules[*].http.paths[*].backend.service.port.name", doc)
            ]

        if minor < 19:
            assert doc["apiVersion"] == "networking.k8s.io/v1beta1"
            assert "release-name-prometheus" in [
                name[0] for name in jmespath.search("spec.rules[*].http.paths[*].backend.serviceName", doc)
            ]
            assert "prometheus-data" in [
                port[0] for port in jmespath.search("spec.rules[*].http.paths[*].backend.servicePort", doc)
            ]

    @pytest.mark.parametrize(
        ("domain_prefix", "expected_host"),
        [("dp01", "prometheus.dp01.example.com"), ("", "prometheus.example.com"), (None, "prometheus.example.com")],
    )
    def test_prometheus_ingress_host_domain_prefix(self, domain_prefix, expected_host, kube_version):
        """Data plane installs without a domainPrefix (same cluster as the control plane)
        use prometheus.<baseDomain> instead of prometheus.<domainPrefix>.<baseDomain>."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data", "domainPrefix": domain_prefix},
                    "tlsSecret": "my-tls-secret",
                },
            },
            show_only=["charts/prometheus/templates/ingress.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["spec"]["rules"][0]["host"] == expected_host
        assert doc["spec"]["tls"][0]["hosts"] == [expected_host]

    @pytest.mark.parametrize(
        ("domain_prefix", "expected_host"),
        [("dp01", "prom-proxy.dp01.example.com"), ("", "prom-proxy.example.com"), (None, "prom-proxy.example.com")],
    )
    def test_prometheus_federate_ingress_host_domain_prefix(self, domain_prefix, expected_host, kube_version):
        """Data plane installs without a domainPrefix (same cluster as the control plane)
        use prom-proxy.<baseDomain> instead of prom-proxy.<domainPrefix>.<baseDomain>."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data", "domainPrefix": domain_prefix},
                    "tlsSecret": "my-tls-secret",
                },
            },
            show_only=["charts/prometheus/templates/prometheus-federate-ingress.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["spec"]["rules"][0]["host"] == expected_host
        assert doc["spec"]["tls"][0]["hosts"] == [expected_host]
