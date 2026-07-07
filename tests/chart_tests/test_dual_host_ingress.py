"""Tests for dual-host ingress & TLS SAN templating (PINF-809).

When `global.controlPlaneHA.enabled` is set, each customer-facing ingress (public,
houston, grafana, alertmanager, prometheus) emits two host families:
  * per-CP admin     — templated from `global.baseDomain` (unchanged)
  * customer-facing  — templated from `global.controlPlaneHA.globalBaseDomain`
Both the `rules[].host` list and the mirrored `spec.tls[].hosts` list (TLS SAN
expansion) cover both families. With HA off, only the per-CP family is rendered
(single-CP installs are unchanged).
"""

import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

PUBLIC_INGRESS = "charts/astronomer/templates/ingress.yaml"
HOUSTON_INGRESS = "charts/astronomer/templates/houston/ingress.yaml"
GRAFANA_INGRESS = "charts/grafana/templates/grafana-ingress.yaml"
ALERTMANAGER_INGRESS = "charts/alertmanager/templates/ingress.yaml"
PROMETHEUS_INGRESS = "charts/prometheus/templates/ingress.yaml"

BASE_DOMAIN = "example.com"
GLOBAL_BASE_DOMAIN = "astro.example.com"

# Per ingress: the host(s) expected from baseDomain (per-CP admin family) and from
# globalBaseDomain (customer-facing family). The public ingress emits two hosts per
# family (bare + app); the rest emit one.
INGRESS_HOSTS = {
    PUBLIC_INGRESS: (
        [BASE_DOMAIN, f"app.{BASE_DOMAIN}"],
        [GLOBAL_BASE_DOMAIN, f"app.{GLOBAL_BASE_DOMAIN}"],
    ),
    HOUSTON_INGRESS: ([f"houston.{BASE_DOMAIN}"], [f"houston.{GLOBAL_BASE_DOMAIN}"]),
    GRAFANA_INGRESS: ([f"grafana.{BASE_DOMAIN}"], [f"grafana.{GLOBAL_BASE_DOMAIN}"]),
    ALERTMANAGER_INGRESS: ([f"alertmanager.{BASE_DOMAIN}"], [f"alertmanager.{GLOBAL_BASE_DOMAIN}"]),
    PROMETHEUS_INGRESS: ([f"prometheus.{BASE_DOMAIN}"], [f"prometheus.{GLOBAL_BASE_DOMAIN}"]),
}


def _ha_values(**overrides):
    """global.controlPlaneHA enabled with a valid globalBaseDomain, control plane."""
    cpha = {"enabled": True, "globalBaseDomain": GLOBAL_BASE_DOMAIN}
    cpha.update(overrides)
    return {"global": {"plane": {"mode": "control"}, "baseDomain": BASE_DOMAIN, "controlPlaneHA": cpha}}


def _no_ha_values():
    return {"global": {"plane": {"mode": "control"}, "baseDomain": BASE_DOMAIN}}


def _find_ingress(docs):
    """Return the single Ingress doc from a rendered template (ignores any extra docs)."""
    ingresses = [d for d in docs if d and d.get("kind") == "Ingress"]
    assert len(ingresses) == 1
    return ingresses[0]


def _rule_hosts(ingress):
    return [rule["host"] for rule in ingress["spec"]["rules"]]


def _tls_hosts(ingress):
    hosts = []
    for entry in ingress["spec"].get("tls", []):
        hosts.extend(entry.get("hosts", []))
    return hosts


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
@pytest.mark.parametrize("ingress_file", list(INGRESS_HOSTS))
class TestDualHostIngress:
    def test_ha_off_single_host_family(self, kube_version, ingress_file):
        """HA off: only the per-CP (baseDomain) host family renders — no global hosts."""
        per_cp_hosts, global_hosts = INGRESS_HOSTS[ingress_file]
        ingress = _find_ingress(render_chart(kube_version=kube_version, show_only=[ingress_file], values=_no_ha_values()))
        rule_hosts = _rule_hosts(ingress)
        for host in per_cp_hosts:
            assert host in rule_hosts
        for host in global_hosts:
            assert host not in rule_hosts
        # TLS SAN list must not leak global hosts when HA is off.
        for host in global_hosts:
            assert host not in _tls_hosts(ingress)

    def test_ha_on_both_host_families(self, kube_version, ingress_file):
        """HA on: both per-CP and global host families render in rules and TLS hosts."""
        per_cp_hosts, global_hosts = INGRESS_HOSTS[ingress_file]
        ingress = _find_ingress(render_chart(kube_version=kube_version, show_only=[ingress_file], values=_ha_values()))
        rule_hosts = _rule_hosts(ingress)
        for host in per_cp_hosts + global_hosts:
            assert host in rule_hosts, f"{host} missing from rules of {ingress_file}"
        # TLS SAN expansion mirrors the rule hosts (both families).
        tls_hosts = _tls_hosts(ingress)
        for host in per_cp_hosts + global_hosts:
            assert host in tls_hosts, f"{host} missing from tls.hosts of {ingress_file}"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_prometheus_data_plane_ha_no_global_host(kube_version):
    """Prometheus ingress renders on data planes; globalBaseDomain is control-plane-only.

    A data-plane render with HA enabled (e.g. shared values) and no globalBaseDomain must
    render cleanly and emit no global host (mirrors PINF-768's data-plane guard).
    """
    values = {
        "global": {
            "plane": {"mode": "data", "domainPrefix": "dp"},
            "baseDomain": BASE_DOMAIN,
            "controlPlaneHA": {"enabled": True},
        }
    }
    ingress = _find_ingress(render_chart(kube_version=kube_version, show_only=[PROMETHEUS_INGRESS], values=values))
    rule_hosts = _rule_hosts(ingress)
    assert rule_hosts == [f"prometheus.dp.{BASE_DOMAIN}"]
    assert GLOBAL_BASE_DOMAIN not in " ".join(_tls_hosts(ingress))


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_public_ingress_global_bare_domain_redirect(kube_version):
    """Public ingress redirects the bare global host to app.<globalBaseDomain> (parity with baseDomain)."""
    ingress = _find_ingress(render_chart(kube_version=kube_version, show_only=[PUBLIC_INGRESS], values=_ha_values()))
    snippet = ingress["metadata"]["annotations"]["nginx.ingress.kubernetes.io/configuration-snippet"]
    assert f"if ($host = '{GLOBAL_BASE_DOMAIN}' )" in snippet
    assert f"https://app.{GLOBAL_BASE_DOMAIN}$request_uri" in snippet


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_public_ingress_data_plane_ha_no_global_redirect(kube_version):
    """Public ingress renders on data planes; the global bare-domain redirect is control-plane-only.

    A data-plane render with HA enabled and no globalBaseDomain must not emit the global
    redirect (which would otherwise template `<no value>` into the nginx snippet).
    """
    values = {
        "global": {
            "plane": {"mode": "data"},
            "baseDomain": BASE_DOMAIN,
            "controlPlaneHA": {"enabled": True},
        }
    }
    ingress = _find_ingress(render_chart(kube_version=kube_version, show_only=[PUBLIC_INGRESS], values=values))
    snippet = ingress["metadata"]["annotations"]["nginx.ingress.kubernetes.io/configuration-snippet"]
    assert "<no value>" not in snippet
    assert GLOBAL_BASE_DOMAIN not in snippet
    # Only the per-CP baseDomain redirect should be present.
    assert f"if ($host = '{BASE_DOMAIN}' )" in snippet
