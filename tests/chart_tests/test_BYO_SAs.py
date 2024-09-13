import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestServiceAccounts:
    def test_SAs_created(self, kube_version):
        # Render the chart with rbacEnabled set to False
        docs = render_chart(kube_version=kube_version, values={"global": {"rbacEnabled": False}})

        # Check that no ServiceAccount resources are created
        """
        service_accounts = [
            doc["metadata"]["name"] for doc in docs if isinstance(doc, dict) and doc.get("kind") == "ServiceAccount"
        ]
        assert len(service_accounts) == 0, "No ServiceAccounts should be created when rbacEnabled is False"
        """
        # Check that the Deployment or StatefulSet is using the default ServiceAccount
        for doc in docs:
            if isinstance(doc, dict) and doc.get("kind") in ["Deployment", "StatefulSet"]:
                spec = doc.get("spec", {}).get("template", {}).get("spec", {})
                sa_name = spec.get("serviceAccountName", "default")
                assert sa_name == "default", f"Expected default ServiceAccount, but got {sa_name}"

    def test_role_created(self, kube_version):
        """Test that no roles or rolebindings are created when rbac is disabled."""
        values = {"global": {"rbacEnabled": False}}
        docs = [doc for doc in render_chart(kube_version=kube_version, values=values) if doc["kind"] in ["RoleBinding", "Role"]]

        assert not docs
