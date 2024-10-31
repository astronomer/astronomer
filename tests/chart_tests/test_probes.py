import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart
from tests.chart_tests import get_all_features, get_chart_containers

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
        "alertmanager": default_probes,
        "global": {
            "authSidecar": {"enabled": True, **default_probes},
        },
    },
    "charts/astronomer/templates/astro-ui/astro-ui-deployment.yaml": {"astronomer": {"astroUI": default_probes}},
    "charts/astronomer/templates/cli-install/cli-install-deployment.yaml": {"astronomer": {"cliInstall": default_probes}},
    "charts/astronomer/templates/commander/commander-deployment.yaml": {"astronomer": {"commander": default_probes}},
    "charts/astronomer/templates/houston/api/houston-deployment.yaml": {"astronomer": {
        "houston": {**default_probes, "waitForDB": default_probes, "bootstrapper": default_probes}},
    },
    "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml": {"astronomer": {
        "houston": {"worker": default_probes, "waitForDB": default_probes, "bootstrapper": default_probes}},
    },
    "charts/astronomer/templates/registry/registry-statefulset.yaml": {"astronomer": {"registry": default_probes}},
    "charts/elasticsearch/templates/client/es-client-deployment.yaml": {"elasticsearch": {"client": default_probes}},
    "charts/elasticsearch/templates/data/es-data-statefulset.yaml": {"elasticsearch": {"data": default_probes}},
    "charts/elasticsearch/templates/exporter/es-exporter-deployment.yaml": {"elasticsearch": {"exporter": default_probes}},
    "charts/elasticsearch/templates/master/es-master-statefulset.yaml": {
        "elasticsearch": {"master": default_probes},
        "global": {"authSidecar": {"enabled": True, **default_probes}},
    },
    "charts/elasticsearch/templates/nginx/nginx-es-deployment.yaml": {"elasticsearch": {"nginx": default_probes}},
    "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml": {
        "external-es-proxy": {**default_probes, "awsproxy": default_probes},
        "global": {
            "customLogging": {
                "awsServiceAccountAnnotation": "yo imma let you finish but beyonce had the best annotation ever",
                "enabled": True,
            },
        },
    },
    "charts/fluentd/templates/fluentd-daemonset.yaml": {"fluentd": default_probes},
    "charts/grafana/templates/grafana-deployment.yaml": {"grafana": default_probes},
    "charts/kibana/templates/kibana-deployment.yaml": {
        "kibana": default_probes,
        "global": {"authSidecar": {"enabled": True, **default_probes}},
    },
    "charts/kube-state/templates/kube-state-deployment.yaml": {"kube-state": default_probes},
    "charts/nats/templates/statefulset.yaml": {
        "nats": {"nats": default_probes, "reloader": default_probes, "exporter": {**default_probes, "enabled": True}}
    },
    "charts/nginx/templates/nginx-deployment-default.yaml": {"nginx": {"defaultBackend": default_probes}},
    "charts/nginx/templates/nginx-deployment.yaml": {"nginx": default_probes},
    "charts/pgbouncer/templates/pgbouncer-deployment.yaml": {
        "pgbouncer": default_probes,
        "global": {
            "pgbouncer": {"enabled": True},
        },
    },
    "charts/postgresql/templates/statefulset-slaves.yaml": {
        "postgresql": {
            "postgresqlDatabase": "kitten_picture_db",
            **default_probes,
            "replication": {"enabled": True},
            "metrics": {**default_probes, "enabled": True},
        },
        "global": {"postgresqlEnabled": True},
    },
    "charts/postgresql/templates/statefulset.yaml": {"postgresql": default_probes, "global": {"postgresqlEnabled": True}},
    "charts/prometheus/templates/prometheus-statefulset.yaml": {
        "prometheus": {**default_probes, "configMapReloader": default_probes}
    },
    "charts/prometheus-blackbox-exporter/templates/deployment.yaml": {"prometheus-blackbox-exporter": default_probes},
    "charts/prometheus-node-exporter/templates/daemonset.yaml": {"prometheus-node-exporter": default_probes},
    "charts/prometheus-postgres-exporter/templates/deployment.yaml": {
        "prometheus-postgres-exporter": default_probes,
        "global": {"prometheusPostgresExporterEnabled": True},
    },
    "charts/stan/templates/statefulset.yaml": {"stan": {"stan": {"nats": {**default_probes}}, "exporter": default_probes}},
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
    for container in [
            *docs[0]["spec"]["template"]["spec"]["containers"],
            *docs[0]["spec"]["template"]["spec"].get("initContainers", [])
        ]:
        assert (
            container["livenessProbe"] == default_probes["livenessProbe"]
        ), f"livenessProbe not accurate in {template} container {container['name']}"
        assert (
            container["readinessProbe"] == default_probes["readinessProbe"]
        ), f"readinessProbe not accurate in {template} container {container['name']}"



class TestDefaultProbes:
    """Test the default probes. This test is to ensure we keep the default probes during refactoring."""

    def init_test_probes():
        chart_values = get_all_features()
        containers = {}
        for k8s_version in supported_k8s_versions:
            k8s_version_containers = get_chart_containers(k8s_version, chart_values, [])
            containers = {**containers, **k8s_version_containers}
        return dict(sorted(containers.items()))

    chart_containers = init_test_probes()
    containers = {
        k.removeprefix(f"{supported_k8s_versions[-1]}_release-name-"): v
        for k, v in chart_containers.items()
        if supported_k8s_versions[-1] in k
    }
    current_clp = {k: v["livenessProbe"] for k, v in containers.items() if v.get("livenessProbe")}
    current_crp = {k: v["readinessProbe"] for k, v in containers.items() if v.get("readinessProbe")}

    expected_clp = {
        "alertmanager_auth-proxy": {
            "httpGet": {"path": "/healthz", "port": 8084, "scheme": "HTTP"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
        },
        "astro-ui_astro-ui": {"httpGet": {"path": "/", "port": 8080}, "initialDelaySeconds": 10, "periodSeconds": 10},
        "cli-install_cli-install": {
            "httpGet": {"path": "/healthz", "port": 8080, "scheme": "HTTP"},
            "initialDelaySeconds": 30,
            "timeoutSeconds": 5,
        },
        "commander_commander": {
            "failureThreshold": 5,
            "httpGet": {"path": "/healthz", "port": 8880, "scheme": "HTTP"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
            "successThreshold": 1,
            "timeoutSeconds": 5,
        },
        "elasticsearch-client_es-client": {
            "httpGet": {"path": "/_cluster/health?local=true", "port": 9200},
            "initialDelaySeconds": 90,
        },
        "elasticsearch-data_es-data": {"tcpSocket": {"port": 9300}, "initialDelaySeconds": 20, "periodSeconds": 10},
        "elasticsearch-exporter_metrics-exporter": {
            "httpGet": {"path": "/health", "port": "http"},
            "initialDelaySeconds": 30,
            "timeoutSeconds": 10,
        },
        "elasticsearch-master_es-master": {"tcpSocket": {"port": 9300}},
        "fluentd_fluentd": {
            "exec": {
                "command": [
                    "/bin/bash",
                    "-c",
                    "if (( $(ruby -e \"require 'net/http';require 'uri';uri = URI.parse('http://127.0.0.1:24231/metrics');response = Net::HTTP.get_response(uri);puts response.body\" | grep 'fluentd_output_status_buffer_queue_length{' | awk '{ print ($NF > 8) }') )); then exit 1; fi; exit 0",
                ]
            },
            "failureThreshold": 3,
            "initialDelaySeconds": 30,
            "periodSeconds": 15,
            "successThreshold": 1,
            "timeoutSeconds": 5,
        },
        "grafana_auth-proxy": {
            "httpGet": {"path": "/healthz", "port": 8084, "scheme": "HTTP"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
        },
        "grafana_grafana": {"httpGet": {"path": "/api/health", "port": 3000}, "initialDelaySeconds": 10, "periodSeconds": 10},
        "houston_houston": {
            "httpGet": {"path": "/v1/healthz", "port": 8871},
            "initialDelaySeconds": 30,
            "periodSeconds": 10,
            "failureThreshold": 10,
        },
        "kibana_auth-proxy": {
            "httpGet": {"path": "/healthz", "port": 8084, "scheme": "HTTP"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
        },
        "kube-state_kube-state": {"httpGet": {"path": "/healthz", "port": 8080}, "initialDelaySeconds": 5, "timeoutSeconds": 5},
        "nats_nats": {"httpGet": {"path": "/", "port": 8222}, "initialDelaySeconds": 10, "timeoutSeconds": 5},
        "nginx-default-backend_default-backend": {
            "httpGet": {"path": "/healthz", "port": 8080, "scheme": "HTTP"},
            "initialDelaySeconds": 30,
            "timeoutSeconds": 5,
        },
        "nginx_nginx": {"httpGet": {"path": "/healthz", "port": 10254}, "initialDelaySeconds": 30, "timeoutSeconds": 5},
        "pgbouncer_pgbouncer": {"tcpSocket": {"port": 5432}},
        "postgresql_release-name-postgresql": {
            "exec": {"command": ["sh", "-c", 'exec pg_isready -U "postgres" -h 127.0.0.1 -p 5432']},
            "initialDelaySeconds": 30,
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "successThreshold": 1,
            "failureThreshold": 6,
        },
        "prometheus-blackbox-exporter_blackbox-exporter": {"httpGet": {"path": "/health", "port": "http"}},
        "prometheus-node-exporter_node-exporter": {"httpGet": {"path": "/", "port": 9100}},
        "prometheus-postgres-exporter_prometheus-postgres-exporter": {
            "tcpSocket": {"port": 9187},
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
        },
        "prometheus_auth-proxy": {
            "httpGet": {"path": "/healthz", "port": 8084, "scheme": "HTTP"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
        },
        "prometheus_prometheus": {
            "httpGet": {"path": "/-/healthy", "port": 9090},
            "initialDelaySeconds": 10,
            "periodSeconds": 5,
            "failureThreshold": 3,
            "timeoutSeconds": 1,
        },
        "registry_registry": {
            "httpGet": {"path": "/", "port": 5000},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
            "timeoutSeconds": 5,
        },
        "stan_stan": {"httpGet": {"path": "/streaming/serverz", "port": "monitor"}, "initialDelaySeconds": 10, "timeoutSeconds": 5},
    }

    expected_crp = {
        "alertmanager_alertmanager": {
            "httpGet": {"path": "/#/status", "port": 9093},
            "initialDelaySeconds": 30,
            "timeoutSeconds": 30,
        },
        "alertmanager_auth-proxy": {
            "httpGet": {"path": "/healthz", "port": 8084, "scheme": "HTTP"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
        },
        "astro-ui_astro-ui": {"httpGet": {"path": "/", "port": 8080}, "initialDelaySeconds": 10, "periodSeconds": 10},
        "commander_commander": {"httpGet": {"path": "/healthz", "port": 8880}, "initialDelaySeconds": 10, "periodSeconds": 10},
        "elasticsearch-client_es-client": {
            "httpGet": {"path": "/_cluster/health?local=true", "port": 9200},
            "initialDelaySeconds": 5,
        },
        "elasticsearch-exporter_metrics-exporter": {
            "httpGet": {"path": "/health", "port": "http"},
            "initialDelaySeconds": 10,
            "timeoutSeconds": 10,
        },
        "elasticsearch-master_es-master": {
            "httpGet": {"path": "/_cluster/health?local=true", "port": 9200},
            "initialDelaySeconds": 5,
        },
        "grafana_auth-proxy": {
            "httpGet": {"path": "/healthz", "port": 8084, "scheme": "HTTP"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
        },
        "grafana_grafana": {"httpGet": {"path": "/api/health", "port": 3000}, "initialDelaySeconds": 10, "periodSeconds": 10},
        "houston_houston": {
            "httpGet": {"path": "/v1/healthz", "port": 8871},
            "initialDelaySeconds": 30,
            "periodSeconds": 10,
            "failureThreshold": 10,
        },
        "kibana_auth-proxy": {
            "httpGet": {"path": "/healthz", "port": 8084, "scheme": "HTTP"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
        },
        "nats_nats": {"httpGet": {"path": "/", "port": 8222}, "initialDelaySeconds": 10, "timeoutSeconds": 5},
        "pgbouncer_pgbouncer": {"tcpSocket": {"port": 5432}},
        "postgresql_release-name-postgresql": {
            "exec": {"command": ["sh", "-c", "-e", 'pg_isready -U "postgres" -h 127.0.0.1 -p 5432\n']},
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "successThreshold": 1,
            "failureThreshold": 6,
        },
        "prometheus-blackbox-exporter_blackbox-exporter": {"httpGet": {"path": "/health", "port": "http"}},
        "prometheus-node-exporter_node-exporter": {"httpGet": {"path": "/", "port": 9100}},
        "prometheus-postgres-exporter_prometheus-postgres-exporter": {
            "tcpSocket": {"port": 9187},
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
        },
        "prometheus_auth-proxy": {
            "httpGet": {"path": "/healthz", "port": 8084, "scheme": "HTTP"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
        },
        "prometheus_prometheus": {
            "httpGet": {"path": "/-/ready", "port": 9090},
            "initialDelaySeconds": 10,
            "periodSeconds": 5,
            "failureThreshold": 3,
            "timeoutSeconds": 1,
        },
        "registry_registry": {
            "httpGet": {"path": "/", "port": 5000},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
            "timeoutSeconds": 5,
        },
        "stan_stan": {"httpGet": {"path": "/streaming/serverz", "port": "monitor"}, "initialDelaySeconds": 10, "timeoutSeconds": 5},
    }

    lp_data = zip(current_clp.keys(), current_clp.values(), expected_clp.values())
    lp_ids = current_clp.keys()

    # If any other tests fail, this will not run, so they have to be commented out for this to actually show you where the problem is.
    @pytest.mark.parametrize("current,expected", [(current_clp, expected_clp), (current_crp, expected_crp)])
    def test_probe_lists(self, current, expected):
        """Test the default livenessProbes for each container."""
        set_difference = set(current.keys()) ^ set(expected.keys())
        assert set_difference == set(), f"Containers not in both lists: {set_difference}"

    @pytest.mark.parametrize("container,current,expected", lp_data, ids=lp_ids)
    def test_individual_liveness_probes(self, container, current, expected):
        """Test the default livenessProbes for each container."""
        assert current == expected, f"container {container} has unexpected livenessProbe"

    rp_data = zip(current_crp.keys(), current_crp.values(), expected_crp.values())
    rp_ids = current_crp.keys()

    @pytest.mark.parametrize("container,current,expected", rp_data, ids=rp_ids)
    def test_individual_readiness_probes(self, container, current, expected):
        """Test the default readinessProbes for each container."""
        assert current == expected, f"container {container} has unexpected readinessProbe"
