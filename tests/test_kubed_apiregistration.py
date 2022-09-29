from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestKubedApiservice:
    show_only = ["charts/kubed/templates/kubed-apiregistration.yaml"]

    def test_kubed_apiregistration_defaults(self, kube_version):
        """Test that helm renders a good ClusterRoleBinding template for kubed
        with defaults."""
        docs = render_chart(kube_version=kube_version, show_only=self.show_only)

        assert len(docs) == 3
        assert docs[0]["kind"] == "Secret"
        assert docs[1]["kind"] == "ClusterRoleBinding"
        assert docs[2]["kind"] == "RoleBinding"

    def test_kubed_apiregistration_rbac_disabled(self, kube_version):
        """Test that helm renders a good ClusterRoleBinding template for kubed
        with defaults."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={"global": {"rbacEnabled": False}},
        )

        assert len(docs) == 1
        assert docs[0]["kind"] == "Secret"

    def test_kubed_apiregistration_apiserver_enabled(self, kube_version):
        """Test that helm renders a good ClusterRoleBinding template for kubed
        with defaults."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={"kubed": {"apiserver": {"enabled": True}}},
        )

        assert len(docs) == 4
        assert docs[0]["kind"] == "Secret"
        assert docs[1]["kind"] == "ClusterRoleBinding"
        assert docs[2]["kind"] == "RoleBinding"
        assert docs[3]["kind"] == "APIService"
