from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestKubedClusterrolebinding:
    def test_kubed_clusterrolebinding_defaults(self, kube_version):
        """Test that helm renders a good ClusterRoleBinding template for kubed
        with defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"rbacEnabled": True}},
            show_only=["charts/kubed/templates/kubed-clusterrolebinding.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["apiVersion"] == "rbac.authorization.k8s.io/v1"
        assert doc["metadata"]["name"] == "release-name-kubed"
        assert doc["roleRef"] == {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": "release-name-kubed",
        }
        assert doc["subjects"] == [
            {
                "kind": "ServiceAccount",
                "name": "release-name-kubed",
                "namespace": "default",
            }
        ]

    def test_kubed_clusterrolebinding_rbac_enabled(self, kube_version):
        """Test that helm renders a good ClusterRoleBinding template for kubed
        when rbacEnabled=True."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"rbacEnabled": True}},
            show_only=["charts/kubed/templates/kubed-clusterrolebinding.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ClusterRoleBinding"
        assert doc["apiVersion"] == "rbac.authorization.k8s.io/v1"
        assert doc["metadata"]["name"] == "release-name-kubed"
        assert len(doc["roleRef"]) > 0
        assert len(doc["subjects"]) > 0

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"rbacEnabled": False}},
            show_only=["charts/kubed/templates/kubed-clusterrolebinding.yaml"],
        )

        assert len(docs) == 0
