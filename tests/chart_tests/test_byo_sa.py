import pytest
from deepmerge import always_merger

from tests import git_root_dir, supported_k8s_versions
from tests.utils import get_all_features, get_service_account_name_from_doc
from tests.utils.chart import render_chart


def find_all_pod_manager_templates() -> list[str]:
    """Return a sorted, unique list of all pod manager templates in the chart, relative to git_root_dir."""

    false_positive_filenames = [
        "charts/nats/templates/jetstream-job-scc.yaml",  # Not a job, but the scc for the job
    ]

    return sorted(
        {
            str(x.relative_to(git_root_dir))
            for x in (git_root_dir / "charts").rglob("*")
            if any(substr in x.name for substr in ("deployment", "statefulset", "replicaset", "daemonset", "job"))
            and x.is_file()
            and str(x.relative_to(git_root_dir)) not in false_positive_filenames
        }
    )


pod_managers = [
    "CronJob",
    "DaemonSet",
    "Deployment",
    "Job",
    "StatefulSet",
]


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestServiceAccounts:
    def test_serviceaccount_rbac_disabled(self, kube_version):
        """Test that no ServiceAccounts are rendered when rbac is disabled."""
        docs = render_chart(
            kube_version=kube_version, values={"global": {"rbacEnabled": False}, "nats": {"nats": {"createJetStreamJob": False}}}
        )
        service_account_names = [doc["metadata"]["name"] for doc in docs if doc["kind"] == "ServiceAccount"]
        assert not service_account_names, f"Expected no ServiceAccounts but found {service_account_names}"

    def test_role_created(self, kube_version):
        """Test that no roles or rolebindings are created when rbac is disabled."""
        values = {"global": {"rbacEnabled": False}, "nats": {"nats": {"createJetStreamJob": False}}}

        docs = [doc for doc in render_chart(kube_version=kube_version, values=values) if doc["kind"] in ["RoleBinding", "Role"]]
        assert not docs

    def test_serviceaccount_with_overrides(self, kube_version):
        "Test that if custom SA are added it gets created"
        values = {
            "astronomer": {
                "commander": {"serviceAccount": {"create": "true", "name": "commander-test"}},
                "registry": {"serviceAccount": {"create": "true", "name": "registry-test"}},
                "configSyncer": {"serviceAccount": {"create": "true", "name": "configsyncer-test"}},
                "houston": {"serviceAccount": {"create": "true", "name": "houston-test"}},
                "astroUI": {"serviceAccount": {"create": "true", "name": "astroui-test"}},
            },
            "nats": {"nats": {"serviceAccount": {"create": "true", "name": "nats-test"}}},
            "stan": {"stan": {"serviceAccount": {"create": "true", "name": "stan-test"}}},
            "alertmanager": {"serviceAccount": {"create": "true", "name": "alertmanager-test"}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/astronomer/templates/commander/commander-serviceaccount.yaml",
                "charts/astronomer/templates/registry/registry-serviceaccount.yaml",
                "charts/astronomer/templates/config-syncer/config-syncer-serviceaccount.yaml",
                "charts/astronomer/templates/houston/api/houston-bootstrap-serviceaccount.yaml",
                "charts/astronomer/templates/astro-ui/astro-ui-serviceaccount.yaml",
                "charts/nats/templates/nats-serviceaccount.yaml",
                "charts/stan/templates/stan-serviceaccount.yaml",
                "charts/alertmanager/templates/alertmanager-serviceaccount.yaml",
            ],
        )

        assert len(docs) == 8
        expected_names = {
            "commander-test",
            "registry-test",
            "configsyncer-test",
            "houston-test",
            "astroui-test",
            "alertmanager-test",
        }
        extracted_names = {doc["metadata"]["name"] for doc in docs if "metadata" in doc and "name" in doc["metadata"]}
        assert expected_names.issubset(extracted_names)

    def test_serviceaccount_with_create_disabled(self, kube_version):
        "Test that if SA create disabled"
        values = {
            "global": {
                "postgresqlEnabled": True,
                "customLogging": {"enabled": True},
                "prometheusPostgresExporterEnabled": True,
                "pgbouncer": {"enabled": True},
                "airflowOperator": {"enabled": True},
            },
            "astronomer": {
                "commander": {"serviceAccount": {"create": False}},
                "registry": {"serviceAccount": {"create": False}},
                "configSyncer": {"serviceAccount": {"create": False}},
                "houston": {"serviceAccount": {"create": False}},
                "astroUI": {"serviceAccount": {"create": False}},
            },
            "nats": {"nats": {"serviceAccount": {"create": False}}},
            "stan": {"stan": {"serviceAccount": {"create": False}}},
            "alertmanager": {"serviceAccount": {"create": False}},
            "postgresql": {"serviceAccount": {"create": False}},
            "external-es-proxy": {"serviceAccount": {"create": False}},
            "prometheus-postgres-exporter": {"serviceAccount": {"create": False}},
            "pgbouncer": {"serviceAccount": {"create": False}},
            "vector": {"serviceAccount": {"create": False}},
            "nginx": {"serviceAccount": {"create": False}, "defaultBackend": {"serviceAccount": {"create": False}}},
            "kube-state": {"serviceAccount": {"create": False}},
            "prometheus": {"serviceAccount": {"create": False}},
            "elasticsearch": {"common": {"serviceAccount": {"create": False}}},
            "airflow-operator": {"serviceAccount": {"create": False}},
        }
        show_only = [
            str(path.relative_to(git_root_dir)) for path in git_root_dir.rglob("charts/**/*") if "serviceaccount" in str(path)
        ]
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=show_only,
        )

        assert len(docs) == 0

    def test_serviceaccount_with_annotations(self, kube_version):
        "Test that if SA create enabled and supports user injected annotations"

        annotations = {"app.managedby": "astronomer"}
        values = {
            "global": {
                "postgresqlEnabled": True,
                "customLogging": {"enabled": True},
                "prometheusPostgresExporterEnabled": True,
                "pgbouncer": {"enabled": True},
                "airflowOperator": {"enabled": True},
            },
            "astronomer": {
                "commander": {"serviceAccount": {"create": True, "annotations": annotations}},
                "registry": {"serviceAccount": {"create": True, "annotations": annotations}},
                "configSyncer": {"serviceAccount": {"create": True, "annotations": annotations}},
                "houston": {"serviceAccount": {"create": True, "annotations": annotations}},
                "astroUI": {"serviceAccount": {"create": True, "annotations": annotations}},
            },
            "nats": {"nats": {"serviceAccount": {"create": True, "annotations": annotations}}},
            "stan": {"stan": {"serviceAccount": {"create": True, "annotations": annotations}}},
            "alertmanager": {"serviceAccount": {"create": True, "annotations": annotations}},
            "postgresql": {"serviceAccount": {"create": True, "annotations": annotations}},
            "external-es-proxy": {"serviceAccount": {"create": True, "annotations": annotations}},
            "prometheus-postgres-exporter": {"serviceAccount": {"create": True, "annotations": annotations}},
            "pgbouncer": {"serviceAccount": {"create": True, "annotations": annotations}},
            "fluentd": {"serviceAccount": {"create": True, "annotations": annotations}},
            "vector": {"serviceAccount": {"create": True, "annotations": annotations}},
            "nginx": {
                "serviceAccount": {"create": True, "annotations": annotations},
                "defaultBackend": {"serviceAccount": {"create": False, "annotations": annotations}},
            },
            "kube-state": {"serviceAccount": {"create": True, "annotations": annotations}},
            "prometheus": {"serviceAccount": {"create": True, "annotations": annotations}},
            "elasticsearch": {"common": {"serviceAccount": {"create": True, "annotations": annotations}}},
            "airflow-operator": {"serviceAccount": {"create": True, "annotations": annotations}},
        }
        show_only = [
            str(path.relative_to(git_root_dir)) for path in git_root_dir.rglob("charts/**/*") if "serviceaccount" in str(path)
        ]
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=show_only,
        )
        service_account_annotations = [doc["metadata"]["annotations"] for doc in docs if doc["kind"] == "ServiceAccount"]
        assert annotations in service_account_annotations

    def test_serviceaccount_with_overrides_rolebinding_controlplane(self, kube_version):
        "Test that if custom SA are added it gets created"
        values = {
            "astronomer": {
                "commander": {"serviceAccount": {"create": "true", "name": "commander-test"}},
                "configSyncer": {"serviceAccount": {"create": "true", "name": "configsyncer-test"}},
                "houston": {"serviceAccount": {"create": "true", "name": "houston-test"}},
            },
            "kube-state": {
                "serviceAccount": {"name": "kube-state-test"},
            },
            "vector": {"serviceAccount": {"create": True, "name": "vector-test"}},
            "prometheus": {"serviceAccount": {"name": "prometheus-test"}},
            "nginx": {"serviceAccount": {"name": "nginx-test"}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/astronomer/templates/commander/commander-rolebinding.yaml",
                "charts/astronomer/templates/config-syncer/config-syncer-rolebinding.yaml",
                "charts/astronomer/templates/houston/api/houston-bootstrap-rolebinding.yaml",
                "charts/kube-state/templates/kube-state-rolebinding.yaml",
                "charts/vector/templates/vector-clusterrolebinding.yaml",
                "charts/prometheus/templates/prometheus-rolebinding.yaml",
                "charts/nginx/templates/controlplane/nginx-cp-rolebinding.yaml",
            ],
        )

        assert len(docs) == 7

        expected_names = {
            "commander-test",
            "configsyncer-test",
            "houston-test",
            "kube-state-test",
            "vector-test",
            "prometheus-test",
            "nginx-test-cp",
        }
        extracted_names = {doc["subjects"][0]["name"] for doc in docs if doc.get("subjects")}
        assert expected_names.issubset(extracted_names)

    def test_serviceaccount_with_overrides_rolebinding_dataplane(self, kube_version):
        "Test rolebindings for components that only use dataplane mode"
        values = {
            "global": {"plane": {"mode": "data"}},
            "nginx": {"serviceAccount": {"name": "nginx-test"}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/nginx/templates/dataplane/nginx-dp-rolebinding.yaml"],
        )
        assert len(docs) == 1


@pytest.mark.parametrize(
    "template_name",
    find_all_pod_manager_templates(),
)
def test_default_serviceaccount_names(template_name):
    """Test that default service account names are rendered correctly."""

    default_serviceaccount_names_overrides = {"global": {"rbacEnabled": False}, "postgresql": {"serviceAccount": {"enabled": True}}}
match template_name:
    case _ if "nginx-dp-deployment" in template_name:
        default_serviceaccount_names_overrides["global"]["plane"] = {"mode": "data"}
    case _ if "fluentd-daemonset" in template_name:
        default_serviceaccount_names_overrides["global"]["logging"] = {"collector": "fluentd"}
    values = always_merger.merge(get_all_features(), default_serviceaccount_names_overrides)

    docs = render_chart(show_only=template_name, values=values)
    pm_docs = [doc for doc in docs if doc["kind"] in pod_managers]
    service_accounts = [get_service_account_name_from_doc(doc) for doc in pm_docs]
    assert service_accounts
    allowed_prefixes = ["release-name-", "default"]
    assert all(any(sa_name.startswith(prefix) for prefix in allowed_prefixes) for sa_name in service_accounts), (
        f"Expected all service accounts to start with a standard prefix but found {service_accounts} in {template_name}"
    )


custom_service_account_names = {
    "charts/airflow-operator/templates/manager/controller-manager-deployment.yaml": {
        "airflow-operator": {"serviceAccount": {"create": True, "name": "prothean"}}
    },
    "charts/alertmanager/templates/alertmanager-statefulset.yaml": {
        "alertmanager": {"serviceAccount": {"create": True, "name": "prothean"}}
    },
    "charts/astronomer/templates/astro-ui/astro-ui-deployment.yaml": {
        "astronomer": {"astroUI": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/commander/commander-deployment.yaml": {
        "astronomer": {"commander": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/config-syncer/config-syncer-cronjob.yaml": {
        "astronomer": {"configSyncer": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/api/houston-deployment.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/cronjobs/houston-check-updates-cronjob.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/cronjobs/houston-cleanup-airflow-db-cronjob.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/cronjobs/houston-cleanup-deploy-revisions-cronjob.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/cronjobs/houston-cleanup-cluster-audits-cronjob.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/cronjobs/houston-cleanup-deployments-cronjob.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/cronjobs/houston-cleanup-task-data-cronjob.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/helm-hooks/houston-au-strategy-job.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/helm-hooks/houston-db-migration-job.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/helm-hooks/houston-upgrade-deployments-job.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/registry/registry-statefulset.yaml": {
        "astronomer": {"registry": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/elasticsearch/templates/client/es-client-deployment.yaml": {
        "elasticsearch": {"common": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/elasticsearch/templates/curator/es-curator-cronjob.yaml": {
        "elasticsearch": {"common": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/elasticsearch/templates/data/es-data-statefulset.yaml": {
        "elasticsearch": {"common": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/elasticsearch/templates/exporter/es-exporter-deployment.yaml": {
        "elasticsearch": {"common": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/elasticsearch/templates/master/es-master-statefulset.yaml": {
        "elasticsearch": {"common": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/elasticsearch/templates/nginx/nginx-es-deployment.yaml": {
        "elasticsearch": {"common": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/external-es-proxy/templates/external-es-proxy-deployment.yaml": {
        "external-es-proxy": {"serviceAccount": {"create": True, "name": "prothean"}}
    },
    "charts/nats/templates/jetstream-job.yaml": {
        "nats": {"nats": {"jetstream": {"serviceAccount": {"create": True, "name": "prothean"}}}}
    },
    "charts/nats/templates/statefulset.yaml": {"nats": {"nats": {"serviceAccount": {"create": True, "name": "prothean"}}}},
    "charts/nginx/templates/nginx-deployment-default.yaml": {
        "nginx": {"defaultBackend": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/nginx/templates/controlplane/nginx-cp-deployment.yaml": {
        "nginx": {"serviceAccount": {"create": True, "name": "prothean"}}
    },
    "charts/nginx/templates/dataplane/nginx-dp-deployment.yaml": {
        "nginx": {"serviceAccount": {"create": True, "name": "prothean"}}
    },
    "charts/pgbouncer/templates/pgbouncer-deployment.yaml": {"pgbouncer": {"serviceAccount": {"create": True, "name": "prothean"}}},
    "charts/postgresql/templates/statefulset-slaves.yaml": {"postgresql": {"serviceAccount": {"create": True, "name": "prothean"}}},
    "charts/postgresql/templates/statefulset.yaml": {"postgresql": {"serviceAccount": {"create": True, "name": "prothean"}}},
    "charts/prometheus-postgres-exporter/templates/deployment.yaml": {
        "prometheus-postgres-exporter": {"serviceAccount": {"create": True, "name": "prothean"}}
    },
    "charts/prometheus/templates/prometheus-statefulset.yaml": {
        "prometheus": {"serviceAccount": {"create": True, "name": "prothean"}}
    },
    "charts/stan/templates/statefulset.yaml": {"stan": {"stan": {"serviceAccount": {"create": True, "name": "prothean"}}}},
    "charts/fluentd/templates/fluentd-daemonset.yaml": {
        "global": {"logging": {"collector": "fluentd"}, "plane": {"mode": "data"}},
        "fluentd": {"serviceAccount": {"create": True, "name": "prothean"}},
    },
    "charts/vector/templates/vector-daemonset.yaml": {
        "global": {"logging": {"collector": "vector"}},
        "vector": {"serviceAccount": {"create": True, "name": "prothean"}},
    },
    "charts/kube-state/templates/kube-state-deployment.yaml": {
        "kube-state": {"serviceAccount": {"create": True, "name": "prothean"}}
    },
}


@pytest.mark.parametrize(
    "template_name",
    find_all_pod_manager_templates(),
)
def test_custom_serviceaccount_names(template_name):
    """Test that custom service account names are rendered correctly."""

    values = always_merger.merge(get_all_features(), custom_service_account_names[template_name])
    enable_pgsql_sa = {"postgresql": {"serviceAccount": {"enabled": True}}}
    if "nginx-dp-deployment" in template_name:
        plane_config = {"global": {"plane": {"mode": "data"}}}
        values = always_merger.merge(values, plane_config)
    values = always_merger.merge(values, enable_pgsql_sa)

    docs = render_chart(show_only=template_name, values=values)
    pm_docs = [doc for doc in docs if doc["kind"] in pod_managers]
    service_accounts = [get_service_account_name_from_doc(doc) for doc in pm_docs]
    assert service_accounts
    valid_sa_names = {"prothean", "prothean-cp", "prothean-dp"}
    assert all(sa_name in valid_sa_names for sa_name in service_accounts), (
        f"Expected all service accounts to be 'prothean' but found {service_accounts} in {template_name}"
    )
