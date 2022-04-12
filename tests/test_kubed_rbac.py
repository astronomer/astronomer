from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestKubedRBAC:
    def test_kubed_rbac_enabled_no_namespace_pool(self, kube_version):
        """Test that helm renders a ClusterRole and ClusterRoleBinding for KubeD when RBAC is enabled and namespace pools is disabled"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "rbacEnabled": True,
                    "features": {"namespacePools": {"enabled": False}}
                }
            },
            show_only=[
                "charts/kubed/templates/kubed-rolebinding.yaml",
                "charts/kubed/templates/kubed-role.yaml",
            ],
        )

        assert len(docs) == 2

        role_binding = docs[0]
        assert role_binding["apiVersion"] == "rbac.authorization.k8s.io/v1"
        assert role_binding["metadata"]["name"] == "release-name-kubed"
        assert role_binding["roleRef"] == {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": "release-name-kubed",
        }
        assert role_binding["subjects"] == [
            {
                "kind": "ServiceAccount",
                "name": "release-name-kubed",
                "namespace": "default",
            }
        ]

        role = docs[1]
        assert role["kind"] == "ClusterRole"
        assert role["metadata"]["name"] == "release-name-kubed"

    def test_kubed_rolebinding_rbac_disabled(self, kube_version):
        """Test that helm renders no ClusterRoleBinding template for kubed when rbacEnabled=False."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"rbacEnabled": False}},
            show_only=["charts/kubed/templates/kubed-rolebinding.yaml"],
        )

        assert len(docs) == 0

    def test_kubed_rbac_namespace_pool_enabled(self, kube_version):
        """Test that if namespace pool is enabled, render roles and role binding scoped to airflow namespaces in the pool and Astronomer namespace"""
        namespaces = ["my-ns-1", "my-ns-2"]
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "rbacEnabled": True,
                    "features": {
                        "namespacePools": {
                            "enabled": True,
                            "namespaces": {
                                "names": namespaces
                            }
                        }
                    }
                }
            },
            show_only=[
                "charts/kubed/templates/kubed-role.yaml",
                "charts/kubed/templates/kubed-rolebinding.yaml"
            ]
        )

        assert len(docs) == 6

        expected_namespaces = [*namespaces, "default"]

        # assertions on Role objects
        for i in range(0, 3):
            role = docs[i]

            assert role["kind"] == "Role"
            assert len(role["rules"]) > 0
            assert role["metadata"]["namespace"] == expected_namespaces[i]

        for i in range(3, 6):
            role_binding = docs[i]

            expected_subject = {
                "kind": "ServiceAccount",
                "name": "release-name-kubed",
                "namespace": "default",
            }
            expected_role = {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": "release-name-kubed",
            }

            assert role_binding["kind"] == "RoleBinding"
            assert role_binding["metadata"]["namespace"] == expected_namespaces[i - 3]
            assert role_binding["roleRef"] == expected_role
            assert role_binding["subjects"][0] == expected_subject

