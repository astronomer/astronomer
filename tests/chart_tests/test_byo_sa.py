import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestServiceAccounts:
    def test_serviceaccount_rbac_disabled(self, kube_version):
        # Render the chart with rbacEnabled set to False
        docs = render_chart(
            kube_version=kube_version, values={"global": {"rbacEnabled": False}, "nats": {"nats": {"createJetStreamJob": False}}}
        )

        # Check that no ServiceAccount resources are created

        service_accounts = [
            doc["metadata"]["name"] for doc in docs if isinstance(doc, dict) and doc.get("kind") == "ServiceAccount"
        ]
        assert len(service_accounts) == 0, "No ServiceAccounts should be created when rbacEnabled is False"

        # Check that the Deployment or StatefulSet is using the default ServiceAccount
        sa_name = ""
        # print(docs)
        for doc in docs:
            if doc.get("kind") in ["Deployment", "StatefulSet"]:
                assert (
                    sa_name == doc["metadata"]["name"] for doc in docs if doc.get("kind") == "ServiceAccount"
                ), f"Expected default ServiceAccount, but got {sa_name}"

    def test_role_created(self, kube_version):
        """Test that no roles or rolebindings are created when rbac is disabled."""
        values = {"global": {"rbacEnabled": False}, "nats": {"nats": {"createJetStreamJob": False}}}

        docs = [doc for doc in render_chart(kube_version=kube_version, values=values) if doc["kind"] in ["RoleBinding", "Role"]]
        print(docs)
        assert not docs
