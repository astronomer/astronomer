import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

# External-es-proxy and prometheus-postgres-exporter are set false by default,
# needs additional work on creating test cases for future
show_only = [
    "charts/postgresql/templates/networkpolicy.yaml",
    # 'charts/external-es-proxy/templates/external-es-proxy-networkpolicy.yaml',
    # 'charts/prometheus-postgres-exporter/templates/networkpolicy.yaml',
    "charts/alertmanager/templates/alertmanager-networkpolicy.yaml",
    "charts/grafana/templates/grafana-networkpolicy.yaml",
    "charts/nats/templates/networkpolicy.yaml",
    "charts/astronomer/templates/commander/commander-networkpolicy.yaml",
    "charts/astronomer/templates/houston/api/houston-networkpolicy.yaml",
    "charts/astronomer/templates/houston/worker/houston-worker-networkpolicy.yaml",
    "charts/astronomer/templates/registry/registry-networkpolicy.yaml",
    "charts/astronomer/templates/astro-ui/astro-ui-networkpolicy.yaml",
    "charts/nginx/templates/controlplane/nginx-cp-metrics-networkpolicy.yaml",
    "charts/nginx/templates/controlplane/nginx-cp-networkpolicy.yaml",
    "charts/nginx/templates/dataplane/nginx-dp-metrics-networkpolicy.yaml",
    "charts/nginx/templates/dataplane/nginx-dp-networkpolicy.yaml",
    "charts/nginx/templates/nginx-default-backend-networkpolicy.yaml",
    "charts/prometheus/templates/prometheus-networkpolicy.yaml",
    "charts/kube-state/templates/kube-state-networkpolicy.yaml",
    "charts/elasticsearch/templates/master/es-master-networkpolicy.yaml",
    "charts/elasticsearch/templates/nginx/nginx-es-networkpolicy.yaml",
    "charts/elasticsearch/templates/exporter/es-exporter-networkpolicy.yaml",
    "charts/elasticsearch/templates/data/es-data-networkpolicy.yaml",
    "charts/elasticsearch/templates/client/es-client-networkpolicy.yaml",
    "templates/default-deny-network-policy/networkpolicy.yaml",
    "charts/vector/templates/vector-networkpolicy.yaml",
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


@pytest.mark.parametrize("np_enabled, num_of_docs", [(True, 21), (False, 0)])
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
        components = [x["podSelector"]["matchLabels"].get("component") for x in docs[0]["spec"]["ingress"][0]["from"]]
        assert "dag-server" not in components


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_networkpolicy_for_airflow_components(kube_version):
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
    ingress_from = docs[0]["spec"]["ingress"][0]["from"]

    for from_rule in ingress_from:
        if "podSelector" in from_rule and "matchExpressions" in from_rule.get("podSelector", {}):
            for expr in from_rule["podSelector"]["matchExpressions"]:
                if expr.get("key") == "component":
                    components = expr.get("values", [])
                    break

    assert len(components) == 4
    assert "dag-server" in components
    assert "webserver" in components
    assert "api-server" in components
    assert "flower" in components


@pytest.mark.parametrize(
    "kube_version, pgbouncer_enabled",
    [(kube_version, pgbouncer_enabled) for kube_version in supported_k8s_versions for pgbouncer_enabled in (True, False)],
)
def test_houston_networkpolicy_pgbouncer_ingress_rule(kube_version: str, pgbouncer_enabled: bool) -> None:
    """Test that the Houston NetworkPolicy includes the pgbouncer ingress rule only when pgbouncer is enabled."""
    docs = render_chart(
        kube_version=kube_version,
        show_only="charts/astronomer/templates/houston/api/houston-networkpolicy.yaml",
        values={
            "global": {
                "networkPolicy": {"enabled": True},
                "pgbouncer": {"enabled": pgbouncer_enabled},
            }
        },
    )

    assert len(docs) == 1
    from_entries = docs[0]["spec"]["ingress"][0]["from"]

    expected_pgbouncer_peer = {
        "podSelector": {
            "matchLabels": {
                "tier": "astronomer",
                "component": "pgbouncer",
                "release": "release-name",
            }
        }
    }

    if pgbouncer_enabled:
        assert expected_pgbouncer_peer in from_entries
    else:
        assert expected_pgbouncer_peer not in from_entries


@pytest.mark.parametrize(
    "kube_version, pgbouncer_enabled",
    [(kube_version, pgbouncer_enabled) for kube_version in supported_k8s_versions for pgbouncer_enabled in (True, False)],
)
def test_houston_worker_networkpolicy_pgbouncer_ingress_shape(kube_version: str, pgbouncer_enabled: bool) -> None:
    """Test that the Houston Worker NetworkPolicy renders a valid ingress shape based on pgbouncer enablement."""
    docs = render_chart(
        kube_version=kube_version,
        show_only="charts/astronomer/templates/houston/worker/houston-worker-networkpolicy.yaml",
        values={
            "global": {
                "networkPolicy": {"enabled": True},
                "pgbouncer": {"enabled": pgbouncer_enabled},
            }
        },
    )

    assert len(docs) == 1

    if not pgbouncer_enabled:
        # Explicit deny-by-default: Ingress list exists but is empty.
        assert docs[0]["spec"]["ingress"] == []
        return

    expected_from_entry = {
        "podSelector": {
            "matchLabels": {
                "tier": "astronomer",
                "component": "pgbouncer",
                "release": "release-name",
            }
        }
    }
    assert docs[0]["spec"]["ingress"][0]["from"] == [expected_from_entry]


@pytest.mark.parametrize(
    "kube_version, pgbouncer_enabled",
    [(kube_version, pgbouncer_enabled) for kube_version in supported_k8s_versions for pgbouncer_enabled in (True, False)],
)
def test_prometheus_networkpolicy_pgbouncer_ingress_rule(kube_version: str, pgbouncer_enabled: bool) -> None:
    """Test that the Prometheus NetworkPolicy includes the pgbouncer ingress rule only when pgbouncer is enabled."""
    docs = render_chart(
        kube_version=kube_version,
        show_only="charts/prometheus/templates/prometheus-networkpolicy.yaml",
        values={
            "global": {
                "networkPolicy": {"enabled": True},
                "pgbouncer": {"enabled": pgbouncer_enabled},
            }
        },
    )

    assert len(docs) == 1
    from_entries = docs[0]["spec"]["ingress"][0]["from"]

    expected_pgbouncer_peer = {
        "podSelector": {
            "matchLabels": {
                "tier": "astronomer",
                "component": "pgbouncer",
                "release": "release-name",
            }
        }
    }

    if pgbouncer_enabled:
        assert expected_pgbouncer_peer in from_entries
    else:
        assert expected_pgbouncer_peer not in from_entries
