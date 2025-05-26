import pytest

from tests import git_root_dir
from tests.chart_tests.helm_template_generator import render_chart

include_kind_list = ["Deployment", "DaemonSet", "StatefulSet", "ReplicaSet"]

default_podsecuritycontext = {
    "fsGroup": 9999,
    "runAsGroup": 9998,
    "runAsUser": 7788,
}

pod_manager_data = {
    "charts/airflow-operator/templates/manager/controller-manager-deployment.yaml": {
        "airflow-operator": {"podSecurityContext": default_podsecuritycontext},
        "global": {
            "airflowOperator": {"enabled": True},
        },
    },
    "charts/alertmanager/templates/alertmanager-statefulset.yaml": {
        "alertmanager": {"podSecurityContext": default_podsecuritycontext},
        "global": {
            "authSidecar": {"enabled": True},
        },
    },
    "charts/astronomer/templates/astro-ui/astro-ui-deployment.yaml": {
        "astronomer": {"astroUI": {"podSecurityContext": default_podsecuritycontext}}
    },
    "charts/astronomer/templates/commander/commander-deployment.yaml": {
        "astronomer": {"commander": {"podSecurityContext": default_podsecuritycontext}}
    },
    "charts/astronomer/templates/houston/api/houston-deployment.yaml": {
        "astronomer": {
            "houston": {
                "podSecurityContext": default_podsecuritycontext,
                "waitForDB": {"podSecurityContext": default_podsecuritycontext},
                "bootstrapper": {"podSecurityContext": default_podsecuritycontext},
            }
        }
    },
    "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml": {
        "astronomer": {
            "houston": {
                "worker": {"podSecurityContext": default_podsecuritycontext},
                "waitForDB": {"podSecurityContext": default_podsecuritycontext},
                "bootstrapper": {"podSecurityContext": default_podsecuritycontext},
            }
        }
    },
    "charts/astronomer/templates/registry/registry-statefulset.yaml": {
        "astronomer": {"registry": {"podSecurityContext": default_podsecuritycontext}}
    },
    "charts/elasticsearch/templates/client/es-client-deployment.yaml": {
        "elasticsearch": {
            "podSecurityContext": default_podsecuritycontext,
        },
        "global": {"openshiftEnabled": False},
    },
    "charts/elasticsearch/templates/data/es-data-statefulset.yaml": {
        "elasticsearch": {
            "podSecurityContext": default_podsecuritycontext,
        }
    },
    "charts/elasticsearch/templates/exporter/es-exporter-deployment.yaml": {
        "elasticsearch": {"exporter": {"podSecurityContext": default_podsecuritycontext}}
    },
    "charts/elasticsearch/templates/master/es-master-statefulset.yaml": {
        "elasticsearch": {
            "podSecurityContext": default_podsecuritycontext,
        },
        "global": {"openshiftEnabled": False},
    },
    "charts/elasticsearch/templates/nginx/nginx-es-deployment.yaml": {
        "elasticsearch": {"nginx": {"podSecurityContext": default_podsecuritycontext}}
    },
    "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml": {
        "external-es-proxy": {"podSecurityContext": default_podsecuritycontext},
        "global": {
            "customLogging": {
                "awsServiceAccountAnnotation": "aws-annotation-value",
                "enabled": True,
            },
        },
    },
    "charts/fluentd/templates/fluentd-daemonset.yaml": {"fluentd": {"pod": {"securityContext": default_podsecuritycontext}}},
    "charts/grafana/templates/grafana-deployment.yaml": {
        "grafana": {
            "podSecurityContext": default_podsecuritycontext,
            "waitForDB": {"podSecurityContext": default_podsecuritycontext},
            "bootstrapper": {"podSecurityContext": default_podsecuritycontext},
        },
    },
    "charts/kibana/templates/kibana-deployment.yaml": {
        "kibana": {"podSecurityContext": default_podsecuritycontext},
        "global": {"authSidecar": {"enabled": True}},
    },
    "charts/kube-state/templates/kube-state-deployment.yaml": {"kube-state": {"podSecurityContext": default_podsecuritycontext}},
    "charts/nats/templates/statefulset.yaml": {
        "nats": {"podSecurityContext": default_podsecuritycontext},
        "reloader": {"podSecurityContext": default_podsecuritycontext},
        "exporter": {"podSecurityContext": default_podsecuritycontext, "enabled": True},
    },
    "charts/nginx/templates/nginx-deployment-default.yaml": {
        "nginx": {"defaultBackend": {"podSecurityContext": default_podsecuritycontext}}
    },
    "charts/nginx/templates/nginx-deployment.yaml": {"nginx": {"podSecurityContext": default_podsecuritycontext}},
    "charts/pgbouncer/templates/pgbouncer-deployment.yaml": {
        "pgbouncer": {"podSecurityContext": default_podsecuritycontext},
        "global": {
            "pgbouncer": {"enabled": True},
        },
    },
    "charts/postgresql/templates/statefulset-slaves.yaml": {
        "postgresql": {
            "securityContext": {"fsGroup": 1001},
            "podSecurityContext": default_podsecuritycontext,
            "replication": {"enabled": True},
        },
        "global": {"postgresqlEnabled": True},
    },
    "charts/prometheus/templates/prometheus-statefulset.yaml": {
        "prometheus": {
            "podSecurityContext": default_podsecuritycontext,
            "configMapReloader": {"podSecurityContext": default_podsecuritycontext},
            "filesdReloader": {"podSecurityContext": default_podsecuritycontext},
        }
    },
    "charts/prometheus-blackbox-exporter/templates/deployment.yaml": {
        "prometheus-blackbox-exporter": {"podSecurityContext": default_podsecuritycontext}
    },
    "charts/prometheus-node-exporter/templates/daemonset.yaml": {
        "prometheus-node-exporter": {"podSecurityContext": default_podsecuritycontext}
    },
    "charts/prometheus-postgres-exporter/templates/deployment.yaml": {
        "prometheus-postgres-exporter": {"podSecurityContext": default_podsecuritycontext},
        "global": {"prometheusPostgresExporterEnabled": True},
    },
    "charts/stan/templates/statefulset.yaml": {
        "stan": {
            "stan": {"nats": {"podSecurityContext": default_podsecuritycontext}},
            "exporter": {"podSecurityContext": default_podsecuritycontext},
            "waitForNatsServer": {"podSecurityContext": default_podsecuritycontext},
        }
    },
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


@pytest.mark.parametrize("template", list(pod_manager_data.keys()))
def test_template_supports_podsecuritycontext(template):
    """Test to Ensure each pod manager template has support for podSecurityContext."""
    values = pod_manager_data[template]

    docs = render_chart(show_only=template, values=values)

    assert len(docs) > 0, f"No documents rendered for {template}"

    for doc in docs:
        if doc.get("kind") in include_kind_list:
            pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})

            security_context = pod_spec.get("securityContext")

            if not security_context:
                print(f"No securityContext found in {template}")
                print(f"Pod spec keys: {pod_spec.keys()}")

            assert security_context is not None, f"No securityContext found in {template}"

            for key, value in default_podsecuritycontext.items():
                assert security_context.get(key) == value, (
                    f"Expected {key}={value} in securityContext, got {security_context.get(key)}"
                )
