import pytest
import yaml

from tests import git_root_dir, supported_k8s_versions
from tests.utils import get_all_features, get_chart_containers, get_containers_by_name
from tests.utils.chart import render_chart

include_kind_list = ["Deployment", "DaemonSet", "StatefulSet", "ReplicaSet", "CronJob", "Job"]

customize_all_probes = yaml.safe_load(
    ((git_root_dir) / "tests" / "chart_tests" / "test_data" / "enable_all_probes.yaml").read_text()
)


class TestCustomProbes:
    docs = render_chart(values=customize_all_probes)
    filtered_docs = [get_containers_by_name(doc) for doc in docs if doc["kind"] in include_kind_list]

    @pytest.mark.parametrize("doc", filtered_docs)
    def test_template_probes_with_custom_values(self, doc):
        """Ensure all containers have the ability to customize liveness probes."""

        for container in doc.values():
            assert "livenessProbe" in container
            assert "readinessProbe" in container
            assert container["livenessProbe"] != {}
            assert container["readinessProbe"] != {}


class TestDefaultProbes:
    """Test the default probes. This test is to ensure we keep the default probes during refactoring."""

    def init_test_probes():
        chart_values = get_all_features()
        containers = {}
        for k8s_version in supported_k8s_versions:
            k8s_version_containers = get_chart_containers(k8s_version, chart_values)
            print(f"Containers before processing: {k8s_version_containers.keys()}")
            containers = {**containers, **k8s_version_containers}
        return dict(sorted(containers.items()))

    chart_containers = init_test_probes()

    # Trim the k8s version because it's not important for this test.
    containers = {
        k.removeprefix(f"{supported_k8s_versions[-1]}_release-name-"): v
        for k, v in chart_containers.items()
        if supported_k8s_versions[-1] in k
    }
    print(f"Container keys after processing: {containers.keys()}")

    # Show only containers that have a liveness or readiness probe.
    current_clp = {k: v["livenessProbe"] for k, v in containers.items() if v.get("livenessProbe")}
    current_crp = {k: v["readinessProbe"] for k, v in containers.items() if v.get("readinessProbe")}

    # Expected container liveness probes. This block should contain all of the expected default liveness probes.
    expected_clp = {
        "alertmanager_auth-proxy": {
            "httpGet": {"path": "/healthz", "port": 8084, "scheme": "HTTP"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
        },
        "aocm_manager": {
            "httpGet": {
                "path": "/healthz",
                "port": 8081,
            }
        },
        "astro-ui_astro-ui": {"httpGet": {"path": "/", "port": 8080}, "initialDelaySeconds": 10, "periodSeconds": 10},
        "commander_commander": {
            "failureThreshold": 5,
            "httpGet": {"path": "/healthz", "port": 8880, "scheme": "HTTP"},
            "initialDelaySeconds": 10,
            "periodSeconds": 10,
            "successThreshold": 1,
            "timeoutSeconds": 5,
        },
        "cp-nginx_nginx": {"httpGet": {"path": "/healthz", "port": 10254}, "initialDelaySeconds": 30, "timeoutSeconds": 5},
        "elasticsearch-client_es-client": {
            "httpGet": {"path": "/_cluster/health?local=true", "port": 9200},
            "initialDelaySeconds": 90,
        },
        "elasticsearch-data_es-data": {"tcpSocket": {"port": 9300}, "initialDelaySeconds": 20, "periodSeconds": 10},
        "elasticsearch-exporter_metrics-exporter": {
            "httpGet": {"path": "/healthz", "port": "http"},
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
        "houston_houston": {
            "httpGet": {"path": "/v1/healthz", "port": 8871},
            "initialDelaySeconds": 30,
            "periodSeconds": 10,
            "failureThreshold": 10,
        },
        "kube-state_kube-state": {"httpGet": {"path": "/healthz", "port": 8080}, "initialDelaySeconds": 5, "timeoutSeconds": 5},
        "nats_nats": {"httpGet": {"path": "/", "port": 8222}, "initialDelaySeconds": 10, "timeoutSeconds": 5},
        "nginx-default-backend_default-backend": {
            "httpGet": {"path": "/healthz", "port": 8080, "scheme": "HTTP"},
            "initialDelaySeconds": 30,
            "timeoutSeconds": 5,
        },
        "pgbouncer_pgbouncer": {"tcpSocket": {"port": 5432}},
        "postgresql-master_release-name-postgresql": {
            "exec": {"command": ["sh", "-c", 'exec pg_isready -U "postgres" -h 127.0.0.1 -p 5432']},
            "initialDelaySeconds": 30,
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "successThreshold": 1,
            "failureThreshold": 6,
        },
        "postgresql-slave_release-name-postgresql": {
            "exec": {"command": ["sh", "-c", 'exec pg_isready -U "postgres" -h 127.0.0.1 -p 5432']},
            "initialDelaySeconds": 30,
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "successThreshold": 1,
            "failureThreshold": 6,
        },
        "prometheus-federation-auth_federation-auth": {
            "httpGet": {"path": "/healthz", "port": 8084},
            "initialDelaySeconds": 10,
            "periodSeconds": 30,
        },
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
        "prometheus_nginx-auth-sidecar": {
            "httpGet": {"path": "/healthz", "port": 8084, "scheme": "HTTP"},
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

    # Expected container readiness probes. This block should contain all of the expected default readiness probes.
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
        "aocm_manager": {
            "httpGet": {
                "path": "/readyz",
                "port": 8081,
            }
        },
        "astro-ui_astro-ui": {"httpGet": {"path": "/", "port": 8080}, "initialDelaySeconds": 10, "periodSeconds": 10},
        "commander_commander": {"httpGet": {"path": "/healthz", "port": 8880}, "initialDelaySeconds": 10, "periodSeconds": 10},
        "elasticsearch-client_es-client": {
            "httpGet": {"path": "/_cluster/health?local=true", "port": 9200},
            "initialDelaySeconds": 5,
        },
        "elasticsearch-exporter_metrics-exporter": {
            "httpGet": {"path": "/healthz", "port": "http"},
            "initialDelaySeconds": 10,
            "timeoutSeconds": 10,
        },
        "elasticsearch-master_es-master": {
            "httpGet": {"path": "/_cluster/health?local=true", "port": 9200},
            "initialDelaySeconds": 5,
        },
        "houston_houston": {
            "httpGet": {"path": "/v1/healthz", "port": 8871},
            "initialDelaySeconds": 30,
            "periodSeconds": 10,
            "failureThreshold": 10,
        },
        "nats_nats": {"httpGet": {"path": "/", "port": 8222}, "initialDelaySeconds": 10, "timeoutSeconds": 5},
        "pgbouncer_pgbouncer": {"tcpSocket": {"port": 5432}},
        "postgresql-master_release-name-postgresql": {
            "exec": {"command": ["sh", "-c", "-e", 'pg_isready -U "postgres" -h 127.0.0.1 -p 5432\n']},
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "successThreshold": 1,
            "failureThreshold": 6,
        },
        "postgresql-slave_release-name-postgresql": {
            "exec": {"command": ["sh", "-c", "-e", 'pg_isready -U "postgres" -h 127.0.0.1 -p 5432\n']},
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "successThreshold": 1,
            "failureThreshold": 6,
        },
        "prometheus-federation-auth_federation-auth": {
            "httpGet": {"path": "/healthz", "port": 8084},
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
        },
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
        "prometheus_nginx-auth-sidecar": {
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

    # liveness probe data and ids
    lp_data = zip(current_clp.keys(), current_clp.values(), expected_clp.values())
    lp_ids = current_clp.keys()

    # If any other tests fail, this will not run, so they have to be commented out for this to actually show you where the problem is.
    @pytest.mark.parametrize("current,expected", [(current_clp, expected_clp), (current_crp, expected_crp)])
    def test_probe_lists(self, current, expected):
        """Test that the list of probes matches between what is rendered by the current chart version and what is expected."""
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
