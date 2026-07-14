import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

NP_FILE = "charts/astronomer/templates/registry/registry-networkpolicy.yaml"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestRegistryNetworkPolicyHoustonCpRefresh:
    def test_unified_mode_adds_houston_cp_refresh_ingress_rule(self, kube_version):
        """houston-cp-refresh podSelector is present in unified mode so the post-upgrade job can reach the registry."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[NP_FILE],
            values={
                "global": {
                    "networkPolicy": {"enabled": True},
                    "plane": {"mode": "unified"},
                }
            },
        )
        assert len(docs) == 1
        ingress_from = docs[0]["spec"]["ingress"][0]["from"]
        cp_refresh_selector = {
            "podSelector": {"matchLabels": {"component": "houston-cp-refresh", "release": "release-name", "tier": "astronomer"}}
        }
        assert cp_refresh_selector in ingress_from

    def test_data_mode_omits_houston_cp_refresh_ingress_rule(self, kube_version):
        """houston-cp-refresh podSelector is absent in data mode, where the job is not rendered."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[NP_FILE],
            values={
                "global": {
                    "networkPolicy": {"enabled": True},
                    "plane": {"mode": "data"},
                }
            },
        )
        assert len(docs) == 1
        all_from_rules = [rule for ingress in docs[0]["spec"]["ingress"] for rule in ingress.get("from", [])]
        components = [r.get("podSelector", {}).get("matchLabels", {}).get("component") for r in all_from_rules]
        assert "houston-cp-refresh" not in components
