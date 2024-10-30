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
            ],
        )

        assert len(docs) == 4

        expected_names = {"commander-test", "registry-test", "configsyncer-test", "houston-test"}
        extracted_names = {doc["metadata"]["name"] for doc in docs if "metadata" in doc and "name" in doc["metadata"]}
        assert expected_names.issubset(extracted_names)

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
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/astronomer/templates/commander/commander-rolebinding.yaml",
                "charts/astronomer/templates/config-syncer/config-syncer-rolebinding.yaml",
                "charts/astronomer/templates/houston/api/houston-bootstrap-rolebinding.yaml",
                "charts/kube-state/templates/kube-state-rolebinding.yaml",
            ],
        )

        assert len(docs) == 4

        expected_names = {"commander-test", "configsyncer-test", "houston-test", "kube-state-test"}
        extracted_names = {doc["subjects"][0]["name"] for doc in docs if doc.get("subjects")}
        assert expected_names.issubset(extracted_names)
