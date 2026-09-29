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
        )

        assert len(docs) == 1

        doc = docs[0]

        annotations = jmespath.search("metadata.annotations", doc)
        assert len(annotations) > 1
        assert annotations["kubernetes.io/ingress.class"] == "release-name-nginx"

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

    def test_ingress_does_not_intercept_404(self, kube_version):
        """Houston is a JSON API (the Airflow proxy path shares this ingress); nginx
        must not replace upstream 404 bodies with the branded default-backend page,
        so custom-http-errors must be absent."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
        )
        assert len(docs) == 1
        annotations = jmespath.search("metadata.annotations", docs[0])
        assert "nginx.ingress.kubernetes.io/custom-http-errors" not in annotations

    def test_ingress_serves_airflow_proxy_regex_path(self, kube_version):
        """The Airflow proxy path is merged into this ingress; use-regex must render
        so the regex path is matched as a regex, and it must coexist with the `/` root."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        annotations = jmespath.search("metadata.annotations", doc)
        assert annotations["nginx.ingress.kubernetes.io/use-regex"] == "true"

        for rule in doc["spec"]["rules"]:
            paths = {p["path"]: p for p in rule["http"]["paths"]}
            assert "/" in paths
            proxy = paths["/v1/deployments/[^/]+/airflow/"]
            assert proxy["pathType"] == "ImplementationSpecific"
            assert proxy["backend"]["service"]["name"] == "release-name-houston"

    def test_airflow_proxy_path_on_both_control_plane_ha_hosts(self, kube_version):
        """Under control-plane HA the ingress emits a second (globalBaseDomain) host
        rule; the Airflow proxy path must render on both, not just the per-CP host."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
            values={
                "global": {
                    "baseDomain": "example.com",
                    "controlPlaneHA": {"enabled": True, "globalBaseDomain": "astro.example.com"},
                }
            },
        )
        assert len(docs) == 1
        rules = docs[0]["spec"]["rules"]
        assert {rule["host"] for rule in rules} == {"houston.example.com", "houston.astro.example.com"}
        for rule in rules:
            proxy_paths = [p for p in rule["http"]["paths"] if p["path"] == "/v1/deployments/[^/]+/airflow/"]
            assert len(proxy_paths) == 1, f"missing Airflow proxy path on host {rule['host']}"
            assert proxy_paths[0]["pathType"] == "ImplementationSpecific"

    def test_use_regex_present_with_auth_sidecar(self, kube_version):
        """The Airflow proxy path is a regex, so use-regex must render regardless of
        auth mode; an auth-sidecar install would otherwise match the path literally."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
            values={"global": {"authSidecar": {"enabled": True}}},
        )
        assert len(docs) == 1
        annotations = jmespath.search("metadata.annotations", docs[0])
        assert annotations["nginx.ingress.kubernetes.io/use-regex"] == "true"

    def test_protect_houston_internal_urls(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        annotations = jmespath.search("metadata.annotations", doc)
        assert (
            annotations["nginx.ingress.kubernetes.io/configuration-snippet"]
            == r"""location ~ ^/v1/(alerts|metrics) {
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
            values={"astronomer": {"houston": {"ingress": {"annotation": custom_annotations}}}},
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        annotations = jmespath.search("metadata.annotations", doc)
        assert annotations["nginx.ingress.kubernetes.io/upstream-keepalive-connections"] == "9999"
        assert annotations["nginx.ingress.kubernetes.io/upstream-keepalive-timeout"] == "7777"

    def test_houston_ingress_with_tls_secret(self, kube_version):
        """Test that houston ingress includes tls with hosts when tlsSecret is set."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
            values={"global": {"baseDomain": "example.com", "tlsSecret": "my-tls-secret"}},
        )

        assert len(docs) == 1
        tls = docs[0]["spec"]["tls"]
        assert len(tls) == 1
        assert tls[0]["secretName"] == "my-tls-secret"
        assert "hosts" in tls[0]
        assert "houston.example.com" in tls[0]["hosts"]

    def test_houston_ingress_without_tls_secret(self, kube_version):
        """Test that houston ingress does not include tls when tlsSecret is empty."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/ingress.yaml"],
            values={"global": {"baseDomain": "example.com", "tlsSecret": ""}},
        )

        assert len(docs) == 1
        assert "tls" not in docs[0]["spec"]
