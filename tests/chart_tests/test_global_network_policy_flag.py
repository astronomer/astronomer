import pytest

from tests.chart_tests.helm_template_generator import render_chart

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
    "charts/elasticsearch/templates/nginx/nginx-es-networkpolicy.yaml",
    "charts/elasticsearch/templates/exporter/es-exporter-networkpolicy.yaml",
    "charts/elasticsearch/templates/data/es-data-networkpolicy.yaml",
    "charts/elasticsearch/templates/client/es-client-networkpolicy.yaml",
    "templates/default-deny-network-policy/networkpolicy.yaml",
]


# Negative test of setting flags to false will not work
# Since the file will always exist in the path ,hence setting
# it to false will not delete the network policy files


@pytest.mark.parametrize("np_enabled, num_of_docs", [(True, 24)])
def test_render_global_network_policy(np_enabled, num_of_docs):
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

    assert (len(docs)) == num_of_docs
