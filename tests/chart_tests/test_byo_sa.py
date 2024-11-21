import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


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
                "install": {"serviceAccount": {"create": "true", "name": "cliinstall-test"}},
            },
            "nats": {"nats": {"serviceAccount": {"create": "true", "name": "nats-test"}}},
            "stan": {"stan": {"serviceAccount": {"create": "true", "name": "stan-test"}}},
            "grafana": {"serviceAccount": {"create": "true", "name": "grafana-test"}},
            "alertmanager": {"serviceAccount": {"create": "true", "name": "alertmanager-test"}},
            "kibana": {"serviceAccount": {"create": "true", "name": "kibana-test"}},
            "prometheus-blackbox-exporter": {"serviceAccount": {"create": "true", "name": "blackbox-test"}},
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
                "charts/astronomer/templates/cli-install/cli-install-serviceaccount.yaml",
                "charts/nats/templates/nats-serviceaccount.yaml",
                "charts/stan/templates/stan-serviceaccount.yaml",
                "charts/grafana/templates/grafana-bootstrap-serviceaccount.yaml",
                "charts/alertmanager/templates/alertmanager-serviceaccount.yaml",
                "charts/kibana/templates/kibana-serviceaccount.yaml",
                "charts/prometheus-blackbox-exporter/templates/blackbox-serviceaccount.yaml",
            ],
        )

        assert len(docs) == 12
        expected_names = {
            "commander-test",
            "registry-test",
            "configsyncer-test",
            "houston-test",
            "astroui-test",
            "grafana-test",
            "alertmanager-test",
            "kibana-test",
            "blackbox-test",
        }
        extracted_names = {doc["metadata"]["name"] for doc in docs if "metadata" in doc and "name" in doc["metadata"]}
        assert expected_names.issubset(extracted_names)
        assert all(True == doc["automountServiceAccountToken"] for doc in docs if "automountServiceAccountToken" in doc)

    def test_serviceaccount_with_overrides_rolebinding(self, kube_version):
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
            "fluentd": {"serviceAccount": {"name": "fluentd-test"}},
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
                "charts/fluentd/templates/fluentd-clusterrolebinding.yaml",
                "charts/prometheus/templates/prometheus-rolebinding.yaml",
                "charts/nginx/templates/nginx-rolebinding.yaml",
                "charts/grafana/templates/grafana-bootstrap-rolebinding.yaml",
            ],
        )

        assert len(docs) == 8

        expected_names = {
            "commander-test",
            "configsyncer-test",
            "houston-test",
            "kube-state-test",
            "fluentd-test",
            "prometheus-test",
            "nginx-test",
            "grafana-test",
        }
        extracted_names = {doc["subjects"][0]["name"] for doc in docs if doc.get("subjects")}
        assert expected_names.issubset(extracted_names)
