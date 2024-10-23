import pytest

from tests import git_root_dir
from tests.chart_tests.helm_template_generator import render_chart

include_kind_list = ["Deployment", "DaemonSet", "StatefulSet", "ReplicaSet"]


pod_manager_data = {
    "charts/alertmanager/templates/alertmanager-statefulset.yaml": {"foo": "bar"},
    "charts/astronomer/templates/astro-ui/astro-ui-deployment.yaml": {"foo": "bar"},
    "charts/astronomer/templates/cli-install/cli-install-deployment.yaml": {"foo": "bar"},
    "charts/astronomer/templates/commander/commander-deployment.yaml": {"foo": "bar"},
    "charts/astronomer/templates/houston/api/houston-deployment.yaml": {"foo": "bar"},
    "charts/astronomer/templates/houston/cronjobs/houston-cleanup-deployments-cronjob.yaml": {"foo": "bar"},
    "charts/astronomer/templates/houston/helm-hooks/houston-upgrade-deployments-job.yaml": {"foo": "bar"},
    "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml": {"foo": "bar"},
    "charts/astronomer/templates/registry/registry-statefulset.yaml": {"foo": "bar"},
    "charts/elasticsearch/templates/client/es-client-deployment.yaml": {"foo": "bar"},
    "charts/elasticsearch/templates/data/es-data-statefulset.yaml": {"foo": "bar"},
    "charts/elasticsearch/templates/exporter/es-exporter-deployment.yaml": {"foo": "bar"},
    "charts/elasticsearch/templates/master/es-master-statefulset.yaml": {"foo": "bar"},
    "charts/elasticsearch/templates/nginx/nginx-es-deployment.yaml": {"foo": "bar"},
    "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml": {"foo": "bar"},
    "charts/fluentd/templates/fluentd-daemonset.yaml": {"foo": "bar"},
    "charts/grafana/templates/grafana-deployment.yaml": {"foo": "bar"},
    "charts/kibana/templates/kibana-deployment.yaml": {"foo": "bar"},
    "charts/kube-state/templates/kube-state-deployment.yaml": {"foo": "bar"},
    "charts/nats/templates/statefulset.yaml": {"foo": "bar"},
    "charts/nginx/templates/nginx-deployment-default.yaml": {"foo": "bar"},
    "charts/nginx/templates/nginx-deployment.yaml": {"foo": "bar"},
    "charts/pgbouncer/templates/pgbouncer-deployment.yaml": {"foo": "bar"},
    "charts/postgresql/templates/statefulset-slaves.yaml": {"foo": "bar"},
    "charts/postgresql/templates/statefulset.yaml": {"foo": "bar"},
    "charts/prometheus/templates/prometheus-statefulset.yaml": {"foo": "bar"},
    "charts/prometheus-blackbox-exporter/templates/deployment.yaml": {"foo": "bar"},
    "charts/prometheus-node-exporter/templates/daemonset.yaml": {"foo": "bar"},
    "charts/prometheus-postgres-exporter/templates/deployment.yaml": {"foo": "bar"},
    "charts/stan/templates/statefulset.yaml": {"foo": "bar"},
}


def find_all_pod_manager_templates() -> list[str]:
    """Return a sorted, unique list of all pod manager templates in the chart, relative to git_root_dir."""

    return sorted(
        {
            str(x.relative_to(git_root_dir))
            for x in (git_root_dir / "charts").rglob("*")
            if any(sub in x.name for sub in ("deployment", "statefulset", "replicaset", "daemonset"))
        }
    )


def test_pod_manager_list(pod_manager_templates=find_all_pod_manager_templates(), pod_manager_list=pod_manager_data.keys()):
    """Make sure we are not adding pod manager templates that are not being tested here."""
    assert pod_manager_templates == sorted(pod_manager_list)


@pytest.mark.parametrize("template,values", zip(pod_manager_data.keys(), pod_manager_data.values()), ids=pod_manager_data.keys())
class TestProbes:
    def test_template_probes_with_custom_values(self, template, values):
        """Ensure all containers have the ability to customize liveness probes."""

        docs = render_chart(show_only=template, values=values)
        assert len(docs) == 1
        for container in docs[0]["spec"]["template"]["spec"]["containers"]:
            assert "livenessProbe" in container
            assert "readinessProbe" in container
