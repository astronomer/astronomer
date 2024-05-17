import pytest

from tests.chart_tests.helm_template_generator import render_chart
from tests import supported_k8s_versions

# External-es-proxy and prometheus-postgres-exporter are set false by default,
# needs additional work on creating test cases for future
show_only = [
    "charts/postgresql/templates/networkpolicy.yaml",
    # 'charts/external-es-proxy/templates/external-es-proxy-networkpolicy.yaml',
    # 'charts/prometheus-postgres-exporter/templates/networkpolicy.yaml',
    "charts/fluentd/templates/fluentd-networkpolicy.yaml",
    "charts/kibana/templates/kibana-networkpolicy.yaml",
    "charts/alertmanager/templates/alertmanager-networkpolicy.yaml",
    "charts/grafana/templates/grafana-networkpolicy.yaml",
    "charts/stan/templates/stan-networkpolicy.yaml",
    "charts/nats/templates/networkpolicy.yaml",
    "charts/astronomer/templates/commander/commander-networkpolicy.yaml",
    "charts/astronomer/templates/houston/api/houston-networkpolicy.yaml",
    "charts/astronomer/templates/houston/worker/houston-worker-networkpolicy.yaml",
    "charts/astronomer/templates/registry/registry-networkpolicy.yaml",
    "charts/astronomer/templates/astro-ui/astro-ui-networkpolicy.yaml",
    "charts/astronomer/templates/cli-install/cli-install-networkpolicy.yaml",
    "charts/nginx/templates/nginx-metrics-networkpolicy.yaml",
    "charts/nginx/templates/nginx-networkpolicy.yaml",
    "charts/nginx/templates/nginx-default-backend-networkpolicy.yaml",
    "charts/prometheus/templates/prometheus-networkpolicy.yaml",
    "charts/kube-state/templates/kube-state-networkpolicy.yaml",
    "charts/elasticsearch/templates/master/es-master-networkpolicy.yaml",
    "charts/elasticsearch/templates/nginx/nginx-es-ingress-networkpolicy.yaml",
    "charts/elasticsearch/templates/exporter/es-exporter-networkpolicy.yaml",
    "charts/elasticsearch/templates/data/es-data-networkpolicy.yaml",
    "charts/elasticsearch/templates/client/es-client-networkpolicy.yaml",
    "templates/default-deny-network-policy/networkpolicy.yaml",
    "charts/prometheus-blackbox-exporter/templates/blackbox-networkpolicy.yaml",
]


def test_networkpolicy_disabled():
    """Test that no NetworkPolicies are rendered by default."""
    docs = render_chart(
        values={
            "global": {
                "networkPolicy": {"enabled": False},
                "postgresqlEnabled": True,
            }
        },
    )

    assert not [x for x in docs if x["kind"] == "NetworkPolicy"]


@pytest.mark.parametrize("np_enabled, num_of_docs", [(True, 32), (False, 0)])
def test_networkpolicy_enabled(np_enabled, num_of_docs):
    """Test some things that should apply to all cases."""
    docs = render_chart(
        show_only=show_only,
        values={
            "global": {
                "networkPolicy": {"enabled": np_enabled},
                "postgresqlEnabled": True,
            }
        },
    )

    assert len(docs) == num_of_docs
    if docs:
        components = [
            x["podSelector"]["matchLabels"].get("component")
            for x in docs[0]["spec"]["ingress"][0]["from"]
        ]
        assert "dag-server" not in components


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_networkpolicy_dag_deploy_enabled(kube_version):
    """Test that the dagOnlyDeployment flag configures a NetworkPolicy for its traffic."""
    docs = render_chart(
        show_only="charts/astronomer/templates/houston/api/houston-networkpolicy.yaml",
        values={
            "global": {
                "networkPolicy": {"enabled": True},
                "dagOnlyDeployment": {"enabled": True},
            },
        },
    )

    assert len(docs) == 1

    components = [
        x["podSelector"]["matchLabels"].get("component")
        for x in docs[0]["spec"]["ingress"][0]["from"]
    ]
    assert len(components) == 8
    assert "dag-server" in components
