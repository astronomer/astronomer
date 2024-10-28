import pytest

from tests import git_root_dir
from tests.chart_tests.helm_template_generator import render_chart

include_kind_list = ["Deployment", "DaemonSet", "StatefulSet", "ReplicaSet"]

default_probes = {
    "livenessProbe": {
        "exec": {"command": ["shaka"]},
    },
    "readinessProbe": {
        "exec": {"command": ["shaka"]},
    },
}

pod_manager_data = {
    "charts/alertmanager/templates/alertmanager-statefulset.yaml": {
        "alertmanager": {**default_probes, "authProxy": default_probes}
    },
    "charts/astronomer/templates/astro-ui/astro-ui-deployment.yaml": {"astronomer": {"astro-ui": default_probes}},
    "charts/astronomer/templates/cli-install/cli-install-deployment.yaml": {"astronomer": {"cli-install": default_probes}},
    "charts/astronomer/templates/commander/commander-deployment.yaml": {"astronomer": {"commander": default_probes}},
    "charts/astronomer/templates/houston/api/houston-deployment.yaml": {"astronomer": {"houston": default_probes}},
    "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml": {
        "astronomer": {"houston": {"worker": default_probes}}
    },
    "charts/astronomer/templates/registry/registry-statefulset.yaml": {"astronomer": {"registry": default_probes}},
    "charts/elasticsearch/templates/client/es-client-deployment.yaml": {"elasticsearch": {"client": default_probes}},
    "charts/elasticsearch/templates/data/es-data-statefulset.yaml": {"elasticsearch": {"data": default_probes}},
    "charts/elasticsearch/templates/exporter/es-exporter-deployment.yaml": {"elasticsearch": {"exporter": default_probes}},
    "charts/elasticsearch/templates/master/es-master-statefulset.yaml": {"elasticsearch": {"master": default_probes}},
    "charts/elasticsearch/templates/nginx/nginx-es-deployment.yaml": {"elasticsearch": {"nginx-es": default_probes}},
    "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml": {"external-es-proxy": default_probes},
    "charts/fluentd/templates/fluentd-daemonset.yaml": {"fluentd": default_probes},
    "charts/grafana/templates/grafana-deployment.yaml": {"grafana": default_probes},
    "charts/kibana/templates/kibana-deployment.yaml": {"kibana": default_probes},
    "charts/kube-state/templates/kube-state-deployment.yaml": {"kube-state": default_probes},
    "charts/nats/templates/statefulset.yaml": {"nats": default_probes},
    "charts/nginx/templates/nginx-deployment-default.yaml": {"nginx": default_probes},
    "charts/nginx/templates/nginx-deployment.yaml": {"nginx": default_probes},
    "charts/pgbouncer/templates/pgbouncer-deployment.yaml": {"pgbouncer": default_probes},
    "charts/postgresql/templates/statefulset-slaves.yaml": {"postgres": default_probes},
    "charts/postgresql/templates/statefulset.yaml": {"postgres": default_probes},
    "charts/prometheus/templates/prometheus-statefulset.yaml": {"prometheus": default_probes},
    "charts/prometheus-blackbox-exporter/templates/deployment.yaml": {"prometheus-blackbox-exporter": default_probes},
    "charts/prometheus-node-exporter/templates/daemonset.yaml": {"prometheus-node-exporter": default_probes},
    "charts/prometheus-postgres-exporter/templates/deployment.yaml": {"prometheus-postgres-exporter": default_probes},
    "charts/stan/templates/statefulset.yaml": {"stan": default_probes},
}


def find_all_pod_manager_templates() -> list[str]:
    """Return a sorted, unique list of all pod manager templates in the chart, relative to git_root_dir."""

    return sorted(
        {
            str(x.relative_to(git_root_dir))
            for x in (git_root_dir / "charts").rglob("*")
            if any(sub in x.name for sub in ("deployment", "statefulset", "replicaset", "daemonset")) and "job" not in x.name
        }
    )


def test_pod_manager_list(pod_manager_templates=find_all_pod_manager_templates(), pod_manager_list=pod_manager_data.keys()):
    """Make sure we are not adding pod manager templates that are not being tested here."""
    assert pod_manager_templates == sorted(pod_manager_list)


@pytest.mark.parametrize("template,values", zip(pod_manager_data.keys(), pod_manager_data.values()), ids=pod_manager_data.keys())
def test_template_probes_with_custom_values(template, values):
    """Ensure all containers have the ability to customize liveness probes."""

    docs = render_chart(show_only=template, values=values)
    assert len(docs) == 1
    for container in docs[0]["spec"]["template"]["spec"]["containers"]:
        assert (
            container["livenessProbe"] == default_probes["livenessProbe"]
        ), f"livenessProbe not accurate in {template} container {container['name']}"
        assert (
            container["readinessProbe"] == default_probes["readinessProbe"]
        ), f"readinessProbe not accurate in {template} container {container['name']}"


@pytest.mark.parametrize("template,values", zip(pod_manager_data.keys(), pod_manager_data.values()), ids=pod_manager_data.keys())
def test_probes_with_default_values(template):
    """Ensure some templates have default probes."""
