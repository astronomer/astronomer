import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

NP_FILE = "charts/astronomer/templates/commander/commander-networkpolicy.yaml"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestCommanderNetworkPolicyDataplaneFailover:
    def test_dataplane_failover_enabled_adds_pilot_ingress_rule(self, kube_version):
        """Pilot podSelector is added to ingress when dataPlaneFailover is enabled in data plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[NP_FILE],
            values={
                "global": {
                    "networkPolicy": {"enabled": True},
                    "plane": {"mode": "data"},
                    "dataPlaneFailover": {"enabled": True},
                }
            },
        )
        assert len(docs) == 1
        ingress_from = docs[0]["spec"]["ingress"][0]["from"]
        pilot_selector = {"podSelector": {"matchLabels": {"component": "pilot", "release": "astronomer", "tier": "astronomer"}}}
        assert pilot_selector in ingress_from

    def test_dataplane_failover_disabled_omits_pilot_ingress_rule(self, kube_version):
        """Pilot podSelector is absent when dataPlaneFailover is disabled in data plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[NP_FILE],
            values={
                "global": {
                    "networkPolicy": {"enabled": True},
                    "plane": {"mode": "data"},
                    "dataPlaneFailover": {"enabled": False},
                }
            },
        )
        assert len(docs) == 1
        ingress_from = docs[0]["spec"]["ingress"][0]["from"]
        components = [r.get("podSelector", {}).get("matchLabels", {}).get("component") for r in ingress_from]
        assert "pilot" not in components

    def test_dataplane_failover_enabled_unified_mode_omits_pilot_ingress_rule(self, kube_version):
        """Pilot podSelector is not added in unified mode even when dataPlaneFailover is enabled."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[NP_FILE],
            values={
                "global": {
                    "networkPolicy": {"enabled": True},
                    "plane": {"mode": "unified"},
                    "dataPlaneFailover": {"enabled": True},
                }
            },
        )
        assert len(docs) == 1
        all_from_rules = [rule for ingress in docs[0]["spec"]["ingress"] for rule in ingress.get("from", [])]
        components = [r.get("podSelector", {}).get("matchLabels", {}).get("component") for r in all_from_rules]
        assert "pilot" not in components

    def test_dataplane_failover_enabled_with_auth_sidecar_adds_pilot_ingress_rule(self, kube_version):
        """Pilot podSelector is added even when authSidecar is enabled, as long as dataPlaneFailover is enabled."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[NP_FILE],
            values={
                "global": {
                    "networkPolicy": {"enabled": True},
                    "plane": {"mode": "data"},
                    "dataPlaneFailover": {"enabled": True},
                    "authSidecar": {"enabled": True},
                }
            },
        )
        assert len(docs) == 1
        ingress_from = docs[0]["spec"]["ingress"][0]["from"]
        pilot_selector = {"podSelector": {"matchLabels": {"component": "pilot", "release": "astronomer", "tier": "astronomer"}}}
        assert pilot_selector in ingress_from
