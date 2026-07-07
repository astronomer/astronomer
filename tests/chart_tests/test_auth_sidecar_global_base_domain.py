"""Tests for the auth-sidecar / commander-gRPC chart gaps in control-plane HA (PINF-894, PINF-895).

Sibling to test_auth_flow_global_base_domain.py. Two auth-sidecar / BYO-ingress
surfaces still assumed the per-CP host under control-plane HA:

The three monitoring auth-sidecar nginx configmaps (prometheus / alertmanager /
grafana) templated the auth subrequest `Host`, the auth `proxy_pass`, and the login `302`
redirect from `global.baseDomain`. Under HA the customer enters via the global host and the
session cookie is scoped to `controlPlaneHA.globalBaseDomain`, so these must resolve to the
global host.

The commander gRPC ingress emitted `backend-protocol: GRPC` and
`enable-http2: true` only in the auth-sidecar-off branch, so auth-sidecar installs lost the
CP->DP gRPC/HTTP-2 backend protocol unless manually patched. Both annotations are now
emitted unconditionally.
"""

import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

PROMETHEUS_CONFIGMAP = "charts/prometheus/templates/prometheus-auth-sidecar-configmap.yaml"
ALERTMANAGER_CONFIGMAP = "charts/alertmanager/templates/alertmanager-auth-sidecar-configmap.yaml"
GRAFANA_CONFIGMAP = "charts/grafana/templates/grafana-auth-sidecar-configmap.yaml"

AUTH_SIDECAR_CONFIGMAPS = [PROMETHEUS_CONFIGMAP, ALERTMANAGER_CONFIGMAP, GRAFANA_CONFIGMAP]

COMMANDER_GRPC_INGRESS = "charts/astronomer/templates/commander/commander-grpc-ingress.yaml"

BASE_DOMAIN = "example.com"
GLOBAL_BASE_DOMAIN = "astro.example.com"

BACKEND_PROTOCOL = "nginx.ingress.kubernetes.io/backend-protocol"
ENABLE_HTTP2 = "nginx.ingress.kubernetes.io/enable-http2"


def _auth_sidecar_values(plane_mode, *, ha=False, global_base_domain=None):
    cpha = {}
    if ha:
        cpha["enabled"] = True
    if global_base_domain is not None:
        cpha["globalBaseDomain"] = global_base_domain
    global_values = {
        "plane": {"mode": plane_mode},
        "baseDomain": BASE_DOMAIN,
        "authSidecar": {"enabled": True},
    }
    if cpha:
        global_values["controlPlaneHA"] = cpha
    return {"global": global_values}


def _nginx_conf(docs):
    """Return the default.conf string from the rendered auth-sidecar ConfigMap."""
    configmaps = [d for d in docs if d and d.get("kind") == "ConfigMap"]
    assert len(configmaps) == 1
    return configmaps[0]["data"]["default.conf"]


def _assert_auth_urls_use(conf, domain):
    """All three auth-sidecar URL refs (Host header, auth proxy_pass, login 302) resolve to `domain`."""
    assert f"Host houston.{domain};" in conf
    assert f"https://houston.{domain}/v1/authorization" in conf
    assert f"https://app.{domain}/login?rd=" in conf


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
@pytest.mark.parametrize("configmap_file", AUTH_SIDECAR_CONFIGMAPS)
class TestAuthSidecarGlobalBaseDomain:
    """PINF-894: Host header, auth proxy_pass, and login 302 redirect on all three configmaps."""

    def test_ha_on_uses_global_host(self, kube_version, configmap_file):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[configmap_file],
            values=_auth_sidecar_values("control", ha=True, global_base_domain=GLOBAL_BASE_DOMAIN),
        )
        _assert_auth_urls_use(_nginx_conf(docs), GLOBAL_BASE_DOMAIN)

    def test_ha_off_uses_base_domain(self, kube_version, configmap_file):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[configmap_file],
            values=_auth_sidecar_values("control"),
        )
        conf = _nginx_conf(docs)
        _assert_auth_urls_use(conf, BASE_DOMAIN)
        # No broken empty-host URLs (regression guard on the fallback path).
        assert "houston./v1/authorization" not in conf
        assert "app./login" not in conf


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestCommanderGrpcIngressProtocolAnnotations:
    """PINF-895: commander gRPC ingress keeps backend-protocol/HTTP-2 in every mode."""

    def _annotations(self, kube_version, *, auth_sidecar):
        global_values = {"plane": {"mode": "data"}, "baseDomain": BASE_DOMAIN}
        if auth_sidecar:
            global_values["authSidecar"] = {"enabled": True}
        docs = render_chart(
            kube_version=kube_version,
            show_only=[COMMANDER_GRPC_INGRESS],
            values={"global": global_values},
        )
        return docs[0]["metadata"]["annotations"]

    def test_auth_sidecar_on_keeps_grpc_annotations(self, kube_version):
        """Auth-sidecar mode must render gRPC/HTTP-2 without a manual commander.ingress.annotation."""
        annotations = self._annotations(kube_version, auth_sidecar=True)
        assert annotations[BACKEND_PROTOCOL] == "GRPC"
        assert annotations[ENABLE_HTTP2] == "true"

    def test_auth_sidecar_off_keeps_grpc_annotations(self, kube_version):
        """Regression guard: default (non-auth-sidecar) mode still has both annotations."""
        annotations = self._annotations(kube_version, auth_sidecar=False)
        assert annotations[BACKEND_PROTOCOL] == "GRPC"
        assert annotations[ENABLE_HTTP2] == "true"
