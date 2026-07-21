import pytest
from deepmerge import always_merger

from tests import git_root_dir, supported_k8s_versions
from tests.utils import (
    find_all_pod_manager_templates,
    get_all_features,
    get_service_account_name_from_doc,
    pod_managers,
)
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestServiceAccounts:
    def test_serviceaccount_rbac_disabled(self, kube_version):
        """Test that no ServiceAccounts are rendered when rbac is disabled."""
        docs = render_chart(kube_version=kube_version, values={"global": {"rbac": {"enabled": False}}})
        service_account_names = [doc["metadata"]["name"] for doc in docs if doc["kind"] == "ServiceAccount"]
        assert not service_account_names, f"Expected no ServiceAccounts but found {service_account_names}"

    def test_role_created(self, kube_version):
        """Test that no roles or rolebindings are created when rbac is disabled."""
        values = {"global": {"rbac": {"enabled": False}}}

        docs = [doc for doc in render_chart(kube_version=kube_version, values=values) if doc["kind"] in ["RoleBinding", "Role"]]
        assert not docs

    def test_serviceaccount_with_overrides(self, kube_version):
        "Test that custom SA names are applied and automountServiceAccountToken defaults to true"
        values = {
            "global": {
                "postgresql": {"enabled": True},
                "nodeExporter": {"enabled": True},
            },
            "astronomer": {
                "commander": {"serviceAccount": {"create": True, "name": "commander-test"}},
                "registry": {"serviceAccount": {"create": True, "name": "registry-test"}},
                "configSyncer": {"serviceAccount": {"create": True, "name": "configsyncer-test"}},
                "houston": {"serviceAccount": {"create": True, "name": "houston-test"}},
                "astroUI": {"serviceAccount": {"create": True, "name": "astroui-test"}},
                "navigator": {"enabled": True, "serviceAccount": {"create": True, "name": "navigator-test"}},
            },
            "nats": {"nats": {"serviceAccount": {"create": True, "name": "nats-test"}}},
            "grafana": {"serviceAccount": {"create": True, "name": "grafana-test"}},
            "alertmanager": {"serviceAccount": {"create": True, "name": "alertmanager-test"}},
            "postgresql": {"serviceAccount": {"create": True, "name": "postgresql-test"}},
            "prometheus-node-exporter": {"serviceAccount": {"create": True, "name": "pne-test"}},
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
                "charts/astronomer/templates/navigator/navigator-serviceaccount.yaml",
                "charts/nats/templates/nats-serviceaccount.yaml",
                "charts/grafana/templates/grafana-bootstrap-serviceaccount.yaml",
                "charts/alertmanager/templates/alertmanager-serviceaccount.yaml",
                "charts/postgresql/templates/serviceaccount.yaml",
                "charts/prometheus-node-exporter/templates/serviceaccount.yaml",
            ],
        )

        assert len(docs) == 11
        expected_names = {
            "commander-test",
            "registry-test",
            "configsyncer-test",
            "houston-test",
            "astroui-test",
            "navigator-test",
            "grafana-test",
            "alertmanager-test",
            "postgresql-test",
            "pne-test",
        }
        extracted_names = {doc["metadata"]["name"] for doc in docs if "metadata" in doc and "name" in doc["metadata"]}
        assert expected_names.issubset(extracted_names)
        assert all(doc["automountServiceAccountToken"] is True for doc in docs)

        # dp-link only renders in control mode, which is mutually exclusive with the
        # data/unified-only components above (commander, registry, configSyncer), so it
        # needs its own render.
        dp_link_docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"dpLink": {"serviceAccount": {"create": True, "name": "dplink-test"}}},
            },
            show_only=["charts/astronomer/templates/dp-link/dp-link-serviceaccount.yaml"],
        )
        assert len(dp_link_docs) == 1
        assert dp_link_docs[0]["metadata"]["name"] == "dplink-test"
        assert dp_link_docs[0]["automountServiceAccountToken"] is True

    def test_automountServiceAccountToken_with_overrides(self, kube_version):
        "Test that automountServiceAccountToken can be overridden to false per component"
        values = {
            "global": {
                "postgresql": {"enabled": True},
                "nodeExporter": {"enabled": True},
            },
            "astronomer": {
                "commander": {"serviceAccount": {"create": True, "name": "commander-test", "automountServiceAccountToken": False}},
                "registry": {"serviceAccount": {"create": True, "name": "registry-test", "automountServiceAccountToken": False}},
                "configSyncer": {
                    "serviceAccount": {"create": True, "name": "configsyncer-test", "automountServiceAccountToken": False}
                },
                "houston": {"serviceAccount": {"create": True, "name": "houston-test", "automountServiceAccountToken": False}},
                "astroUI": {"serviceAccount": {"create": True, "name": "astroui-test", "automountServiceAccountToken": False}},
                "navigator": {
                    "enabled": True,
                    "serviceAccount": {"create": True, "name": "navigator-test", "automountServiceAccountToken": False},
                },
            },
            "nats": {"nats": {"serviceAccount": {"create": True, "name": "nats-test", "automountServiceAccountToken": False}}},
            "grafana": {"serviceAccount": {"create": True, "name": "grafana-test", "automountServiceAccountToken": False}},
            "alertmanager": {
                "serviceAccount": {"create": True, "name": "alertmanager-test", "automountServiceAccountToken": False}
            },
            "postgresql": {"serviceAccount": {"create": True, "name": "postgresql-test", "automountServiceAccountToken": False}},
            "prometheus-node-exporter": {
                "serviceAccount": {"create": True, "name": "pne-test", "automountServiceAccountToken": False}
            },
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
                "charts/astronomer/templates/navigator/navigator-serviceaccount.yaml",
                "charts/nats/templates/nats-serviceaccount.yaml",
                "charts/grafana/templates/grafana-bootstrap-serviceaccount.yaml",
                "charts/alertmanager/templates/alertmanager-serviceaccount.yaml",
                "charts/postgresql/templates/serviceaccount.yaml",
                "charts/prometheus-node-exporter/templates/serviceaccount.yaml",
            ],
        )

        assert len(docs) == 11
        expected_names = {
            "commander-test",
            "registry-test",
            "configsyncer-test",
            "houston-test",
            "astroui-test",
            "navigator-test",
            "grafana-test",
            "alertmanager-test",
            "postgresql-test",
            "pne-test",
        }
        extracted_names = {doc["metadata"]["name"] for doc in docs if "metadata" in doc and "name" in doc["metadata"]}
        assert expected_names.issubset(extracted_names)
        assert all(doc["automountServiceAccountToken"] is False for doc in docs)

        # dp-link only renders in control mode, which is mutually exclusive with the
        # data/unified-only components above (commander, registry, configSyncer), so it
        # needs its own render.
        dp_link_docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {
                    "dpLink": {"serviceAccount": {"create": True, "name": "dplink-test", "automountServiceAccountToken": False}}
                },
            },
            show_only=["charts/astronomer/templates/dp-link/dp-link-serviceaccount.yaml"],
        )
        assert len(dp_link_docs) == 1
        assert dp_link_docs[0]["metadata"]["name"] == "dplink-test"
        assert dp_link_docs[0]["automountServiceAccountToken"] is False

    def test_serviceaccount_with_create_disabled(self, kube_version):
        "Test that if SA create disabled"
        values = {
            "global": {
                "postgresql": {"enabled": True},
                "customLogging": {"enabled": True},
                "prometheusPostgresExporter": {"enabled": True},
                "nodeExporter": {"enabled": True},
                "pgbouncer": {"enabled": True},
                "airflowOperator": {"enabled": True},
            },
            "astronomer": {
                "commander": {"serviceAccount": {"create": False}},
                "registry": {"serviceAccount": {"create": False}},
                "configSyncer": {"serviceAccount": {"create": False}},
                "houston": {"serviceAccount": {"create": False}},
                "astroUI": {"serviceAccount": {"create": False}},
                "dpLink": {"serviceAccount": {"create": False}},
            },
            "nats": {"nats": {"serviceAccount": {"create": False}}},
            "grafana": {"serviceAccount": {"create": False}},
            "alertmanager": {"serviceAccount": {"create": False}},
            "postgresql": {"serviceAccount": {"create": False}},
            "external-es-proxy": {"serviceAccount": {"create": False}},
            "prometheus-postgres-exporter": {"serviceAccount": {"create": False}},
            "prometheus-node-exporter": {"serviceAccount": {"create": False}},
            "pgbouncer": {"serviceAccount": {"create": False}},
            "vector": {"serviceAccount": {"create": False}},
            "nginx": {"serviceAccount": {"create": False}, "defaultBackend": {"serviceAccount": {"create": False}}},
            "kube-state": {"serviceAccount": {"create": False}},
            "prometheus": {"serviceAccount": {"create": False}},
            "elasticsearch": {"common": {"serviceAccount": {"create": False}}},
            "airflow-operator": {"serviceAccount": {"create": False}},
            "external-secrets": {
                "enabled": True,
                "serviceAccount": {"create": False},
                "webhook": {"serviceAccount": {"create": False}},
            },
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
                "postgresql": {"enabled": True},
                "customLogging": {"enabled": True},
                "prometheusPostgresExporter": {"enabled": True},
                "nodeExporter": {"enabled": True},
                "pgbouncer": {"enabled": True},
                "airflowOperator": {"enabled": True},
            },
            "astronomer": {
                "commander": {"serviceAccount": {"create": True, "annotations": annotations}},
                "registry": {"serviceAccount": {"create": True, "annotations": annotations}},
                "configSyncer": {"serviceAccount": {"create": True, "annotations": annotations}},
                "houston": {"serviceAccount": {"create": True, "annotations": annotations}},
                "astroUI": {"serviceAccount": {"create": True, "annotations": annotations}},
                "dpLink": {"serviceAccount": {"create": True, "annotations": annotations}},
            },
            "nats": {"nats": {"serviceAccount": {"create": True, "annotations": annotations}}},
            "grafana": {"serviceAccount": {"create": True, "annotations": annotations}},
            "alertmanager": {"serviceAccount": {"create": True, "annotations": annotations}},
            "postgresql": {"serviceAccount": {"create": True, "annotations": annotations}},
            "external-es-proxy": {"serviceAccount": {"create": True, "annotations": annotations}},
            "prometheus-postgres-exporter": {"serviceAccount": {"create": True, "annotations": annotations}},
            "prometheus-node-exporter": {"serviceAccount": {"create": True, "annotations": annotations}},
            "pgbouncer": {"serviceAccount": {"create": True, "annotations": annotations}},
            "vector": {"serviceAccount": {"create": True, "annotations": annotations}},
            "nginx": {
                "serviceAccount": {"create": True, "annotations": annotations},
                "defaultBackend": {"serviceAccount": {"create": False, "annotations": annotations}},
            },
            "kube-state": {"serviceAccount": {"create": True, "annotations": annotations}},
            "prometheus": {"serviceAccount": {"create": True, "annotations": annotations}},
            "elasticsearch": {"common": {"serviceAccount": {"create": True, "annotations": annotations}}},
            "airflow-operator": {"serviceAccount": {"create": True, "annotations": annotations}},
            "external-secrets": {
                "enabled": True,
                "serviceAccount": {"create": True, "annotations": annotations},
                "webhook": {"serviceAccount": {"create": True, "annotations": annotations}},
            },
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
            "grafana": {"serviceAccount": {"name": "grafana-test"}},
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
                "charts/grafana/templates/grafana-bootstrap-rolebinding.yaml",
            ],
        )

        assert len(docs) == 8

        expected_names = {
            "commander-test",
            "configsyncer-test",
            "houston-test",
            "kube-state-test",
            "vector-test",
            "prometheus-test",
            "nginx-test-cp",
            "grafana-test",
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

    default_serviceaccount_names_overrides = {
        "global": {"rbac": {"enabled": False}, "networkNSLabels": {"enabled": True}},
        "postgresql": {"serviceAccount": {"enabled": True}},
    }
    if any(substring in template_name for substring in data_plane_only_template_substrings):
        default_serviceaccount_names_overrides["global"]["plane"] = {"mode": "data"}
    if any(substring in template_name for substring in control_plane_only_template_substrings):
        default_serviceaccount_names_overrides["global"]["plane"] = {"mode": "control"}
    if any(substring in template_name for substring in ha_only_template_substrings):
        default_serviceaccount_names_overrides["global"]["controlPlaneHA"] = {
            "enabled": True,
            "globalBaseDomain": "example.com",
        }
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
    "charts/astronomer/templates/commander/jwks-hooks/commander-jwks-hooks.yaml": {
        "astronomer": {"commander": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/config-syncer/config-syncer-cronjob.yaml": {
        "astronomer": {"configSyncer": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/dp-link/dp-link-deployment.yaml": {
        "astronomer": {"dpLink": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/navigator/navigator-deployment.yaml": {
        "astronomer": {"navigator": {"enabled": True, "serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/pilot/pilot-deployment.yaml": {
        "astronomer": {"pilot": {"enabled": True, "serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/api/houston-deployment.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/cronjobs/houston-check-runtime-updates.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/cronjobs/houston-populate-daily-task-metrics.yaml": {
        "astronomer": {"houston": {"serviceAccount": {"create": True, "name": "prothean"}}}
    },
    "charts/astronomer/templates/houston/cronjobs/houston-populate-hourly-ta-metrics.yaml": {
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
    "charts/astronomer/templates/houston/cronjobs/houston-sync-dataplane-clusters-cronjob.yaml": {
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
    "charts/astronomer/templates/houston/helm-hooks/houston-cp-refresh-job.yaml": {
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
    "charts/external-secrets/templates/deployment.yaml": {
        "external-secrets": {"enabled": True, "serviceAccount": {"create": True, "name": "prothean"}}
    },
    "charts/grafana/templates/grafana-deployment.yaml": {"grafana": {"serviceAccount": {"create": True, "name": "prothean"}}},
    "charts/nats/templates/jetstream-job.yaml": {
        "nats": {"nats": {"jetStream": {"serviceAccount": {"create": True, "name": "prothean"}}}}
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
    "charts/prometheus/templates/prometheus-federation-auth-deployment.yaml": {
        "prometheus": {"serviceAccount": {"create": True, "name": "prothean"}}
    },
    "charts/prometheus-node-exporter/templates/daemonset.yaml": {
        "prometheus-node-exporter": {"serviceAccount": {"create": True, "name": "prothean"}}
    },
    "charts/vector/templates/vector-daemonset.yaml": {
        "vector": {"serviceAccount": {"create": True, "name": "prothean"}},
    },
    "charts/kube-state/templates/kube-state-deployment.yaml": {
        "kube-state": {"serviceAccount": {"create": True, "name": "prothean"}}
    },
}

# Pod manager templates whose service account name is fixed (not a configurable
# serviceAccount.name), so the custom-name test does not apply to them.
templates_without_custom_service_account = {
    # The namespace labeller job always uses "<release>-labeller"; it is not a BYO-SA component.
    "charts/astronomer/templates/add-labels-to-namespace.yaml",
}

# Templates that only render in the data plane; render them with plane.mode=data.
data_plane_only_template_substrings = (
    "nginx-dp-deployment",
    "prometheus-federation-auth-deployment",
    "pilot-deployment",
    "external-secrets",
    "commander-jwks-hooks",
)

# Templates gated on Control Plane HA; render them with controlPlaneHA.enabled=True.
ha_only_template_substrings = ("houston-cp-refresh-job",)

# Templates that only render in control-plane mode; render them with plane.mode=control.
control_plane_only_template_substrings = ("dp-link-deployment",)


@pytest.mark.parametrize(
    "template_name",
    find_all_pod_manager_templates(),
)
def test_custom_serviceaccount_names(template_name):
    """Test that custom service account names are rendered correctly."""

    if template_name in templates_without_custom_service_account:
        pytest.skip(f"{template_name} uses a fixed service account name and is not BYO-SA configurable")

    # This test is parametrized over find_all_pod_manager_templates(), which discovers every pod
    # manager template by content. Each such template must be classified exactly once: either it
    # supports a configurable serviceAccount.name (an entry in custom_service_account_names giving
    # the values that set it to "prothean"), or its SA name is fixed (listed in
    # templates_without_custom_service_account and skipped above). When a new pod manager template
    # is added to a chart it shows up here automatically, so this guard fails loudly to force that
    # classification instead of dying with a bare KeyError on the dict lookup below.
    assert template_name in custom_service_account_names, (
        f"{template_name} is a pod manager but is not classified for the BYO-SA test. Add it to "
        f"custom_service_account_names with the values that set its serviceAccount.name to 'prothean', "
        f"or, if its service account name is fixed, add it to templates_without_custom_service_account."
    )

    values = always_merger.merge(get_all_features(), custom_service_account_names[template_name])
    enable_pgsql_sa = {"postgresql": {"serviceAccount": {"enabled": True}}}
    if any(substring in template_name for substring in data_plane_only_template_substrings):
        plane_config = {"global": {"plane": {"mode": "data"}}}
        values = always_merger.merge(values, plane_config)
    if any(substring in template_name for substring in control_plane_only_template_substrings):
        plane_config = {"global": {"plane": {"mode": "control"}}}
        values = always_merger.merge(values, plane_config)
    if any(substring in template_name for substring in ha_only_template_substrings):
        ha_config = {"global": {"controlPlaneHA": {"enabled": True, "globalBaseDomain": "example.com"}}}
        values = always_merger.merge(values, ha_config)
    values = always_merger.merge(values, enable_pgsql_sa)

    docs = render_chart(show_only=template_name, values=values)
    pm_docs = [doc for doc in docs if doc["kind"] in pod_managers]
    service_accounts = [get_service_account_name_from_doc(doc) for doc in pm_docs]
    assert service_accounts
    valid_sa_names = {"prothean", "prothean-cp", "prothean-dp"}
    assert all(sa_name in valid_sa_names for sa_name in service_accounts), (
        f"Expected all service accounts to be 'prothean' but found {service_accounts} in {template_name}"
    )
