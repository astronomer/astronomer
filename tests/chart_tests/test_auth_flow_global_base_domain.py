"""Tests for globalBaseDomain precedence on adjacent auth-flow templates (PINF-893).

Follow-up to the dual-host work (PINF-809). Five non-auth-sidecar templates on the auth
flow still hardcoded `global.baseDomain`; under control-plane HA they must resolve to
`global.controlPlaneHA.globalBaseDomain` (the global customer-facing host the session cookie
is scoped to), falling back to `baseDomain` when HA is off:

  * `houston.internalauthurl` helper  -> `auth-url` annotation (shared by the three ingresses)
  * `houston-proxy` helper            -> elasticsearch `proxy_pass`
  * `auth-signin` annotation          -> prometheus / alertmanager / grafana ingresses

Precedence is gated on `and controlPlaneHA.enabled controlPlaneHA.globalBaseDomain`. The
helper fallback to `baseDomain` is now reachable only when HA is off: PINF-1070 makes
globalBaseDomain REQUIRED on every plane (data planes included) whenever HA is enabled, so an
HA-on-without-globalBaseDomain render is a hard failure (validate-controlplane-ha.yaml guard)
rather than the graceful data-plane fallback assumed here originally.
"""

from subprocess import CalledProcessError

import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

PROMETHEUS_INGRESS = "charts/prometheus/templates/ingress.yaml"
ALERTMANAGER_INGRESS = "charts/alertmanager/templates/ingress.yaml"
GRAFANA_INGRESS = "charts/grafana/templates/grafana-ingress.yaml"
ES_NGINX_CONFIGMAP = "charts/elasticsearch/templates/nginx/nginx-es-configmap.yaml"

AUTH_SIGNIN_INGRESSES = [PROMETHEUS_INGRESS, ALERTMANAGER_INGRESS, GRAFANA_INGRESS]

BASE_DOMAIN = "example.com"
GLOBAL_BASE_DOMAIN = "astro.example.com"
DOMAIN_PREFIX = "dp"

AUTH_SIGNIN = "nginx.ingress.kubernetes.io/auth-signin"
AUTH_URL = "nginx.ingress.kubernetes.io/auth-url"


def _values(plane_mode, *, ha=False, global_base_domain=None):
    cpha = {}
    if ha:
        cpha["enabled"] = True
    if global_base_domain is not None:
        cpha["globalBaseDomain"] = global_base_domain
    plane = {"mode": plane_mode}
    # Data-plane hosts are prefixed with domainPrefix (e.g. prometheus.dp.<baseDomain>);
    # set it so data-mode renders match real installs (parity with test_dual_host_ingress.py).
    if plane_mode == "data":
        plane["domainPrefix"] = DOMAIN_PREFIX
    global_values = {"plane": plane, "baseDomain": BASE_DOMAIN}
    if cpha:
        global_values["controlPlaneHA"] = cpha
    return {"global": global_values}


def _es_nginx_conf(docs):
    """Return the nginx.conf string from the rendered elasticsearch nginx ConfigMap."""
    configmaps = [d for d in docs if d and d.get("kind") == "ConfigMap"]
    assert len(configmaps) == 1
    return configmaps[0]["data"]["nginx.conf"]


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestAuthSigninGlobalBaseDomain:
    """auth-signin annotation on the three monitoring ingresses (control plane)."""

    @pytest.mark.parametrize("ingress_file", AUTH_SIGNIN_INGRESSES)
    def test_ha_on_uses_global_host(self, kube_version, ingress_file):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[ingress_file],
            values=_values("control", ha=True, global_base_domain=GLOBAL_BASE_DOMAIN),
        )
        assert docs[0]["metadata"]["annotations"][AUTH_SIGNIN] == f"https://app.{GLOBAL_BASE_DOMAIN}/login"

    @pytest.mark.parametrize("ingress_file", AUTH_SIGNIN_INGRESSES)
    def test_ha_off_uses_base_domain(self, kube_version, ingress_file):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[ingress_file],
            values=_values("control"),
        )
        assert docs[0]["metadata"]["annotations"][AUTH_SIGNIN] == f"https://app.{BASE_DOMAIN}/login"

    def test_ha_on_without_global_base_domain_fails(self, kube_version):
        """PINF-1070: enabling HA without globalBaseDomain is a hard render failure on every plane
        (the shared validate-controlplane-ha.yaml guard), so the data-plane auth-signin fallback
        path is now unreachable. Previously this rendered and fell back to baseDomain, under the
        now-corrected "globalBaseDomain is control-plane-only" framing.
        """
        with pytest.raises(CalledProcessError) as excinfo:
            render_chart(
                kube_version=kube_version,
                show_only=[PROMETHEUS_INGRESS],
                values=_values("data", ha=True),
            )
        assert "global.controlPlaneHA.globalBaseDomain is required" in excinfo.value.stderr.decode("utf-8")


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestAuthUrlGlobalBaseDomain:
    """auth-url annotation via the houston.internalauthurl helper.

    The helper's domain branch is only reachable in data mode (control/unified use the
    in-cluster service URL), so HA resolution is exercised on a data-plane render.
    """

    def test_ha_on_with_global_base_domain_uses_global_host(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[PROMETHEUS_INGRESS],
            values=_values("data", ha=True, global_base_domain=GLOBAL_BASE_DOMAIN),
        )
        assert docs[0]["metadata"]["annotations"][AUTH_URL] == f"https://houston.{GLOBAL_BASE_DOMAIN}/v1/authorization"

    def test_ha_off_uses_base_domain(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[PROMETHEUS_INGRESS],
            values=_values("data"),
        )
        assert docs[0]["metadata"]["annotations"][AUTH_URL] == f"https://houston.{BASE_DOMAIN}/v1/authorization"

    def test_ha_on_without_global_base_domain_fails(self, kube_version):
        """PINF-1070: HA on without globalBaseDomain now fails the render on every plane (the
        shared validate-controlplane-ha.yaml guard), so the data-plane auth-url fallback path is
        unreachable. Previously this rendered and fell back to baseDomain."""
        with pytest.raises(CalledProcessError) as excinfo:
            render_chart(
                kube_version=kube_version,
                show_only=[PROMETHEUS_INGRESS],
                values=_values("data", ha=True),
            )
        assert "global.controlPlaneHA.globalBaseDomain is required" in excinfo.value.stderr.decode("utf-8")


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestHoustonProxyGlobalBaseDomain:
    """elasticsearch proxy_pass via the houston-proxy helper.

    The configmap renders in data/unified mode; unified uses the in-cluster URL, so the
    domain branch is exercised on a data-plane render (parity with the auth-url helper).
    """

    def test_ha_on_with_global_base_domain_uses_global_host(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[ES_NGINX_CONFIGMAP],
            values=_values("data", ha=True, global_base_domain=GLOBAL_BASE_DOMAIN),
        )
        assert f"proxy_pass https://houston.{GLOBAL_BASE_DOMAIN}/v1/elasticsearch;" in _es_nginx_conf(docs)

    def test_ha_off_uses_base_domain(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[ES_NGINX_CONFIGMAP],
            values=_values("data"),
        )
        assert f"proxy_pass https://houston.{BASE_DOMAIN}/v1/elasticsearch;" in _es_nginx_conf(docs)

    def test_ha_on_without_global_base_domain_fails(self, kube_version):
        """PINF-1070: HA on without globalBaseDomain now fails the render on every plane (the
        shared validate-controlplane-ha.yaml guard), so the data-plane proxy_pass fallback path is
        unreachable. Previously this rendered and fell back to baseDomain."""
        with pytest.raises(CalledProcessError) as excinfo:
            render_chart(
                kube_version=kube_version,
                show_only=[ES_NGINX_CONFIGMAP],
                values=_values("data", ha=True),
            )
        assert "global.controlPlaneHA.globalBaseDomain is required" in excinfo.value.stderr.decode("utf-8")
