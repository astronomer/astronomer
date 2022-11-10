from tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions, get_containers_by_name


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerCommander:
    def test_astronomer_commander_deployment_default(self, kube_version):
        """Test that helm renders a good deployment template for
        astronomer/commander."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/commander/commander-deployment.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-commander"
        c_by_name = get_containers_by_name(doc)
        assert len(c_by_name) == 1
        assert c_by_name["commander"]["image"].startswith(
            "quay.io/astronomer/ap-commander:"
        )
        assert c_by_name["commander"]["resources"]["limits"]["memory"] == "2Gi"
        assert c_by_name["commander"]["resources"]["requests"]["memory"] == "1Gi"
        env_vars = {x["name"]: x["value"] for x in c_by_name["commander"]["env"]}
        assert env_vars["COMMANDER_UPGRADE_TIMEOUT"] == "300"

    def test_astronomer_commander_deployment_upgrade_timeout(self, kube_version):
        """Test that helm renders a good deployment template for
        astronomer/commander.

        when upgrade timeout is set
        """
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"commander": {"upgradeTimeout": 600}}},
            show_only=[
                "charts/astronomer/templates/commander/commander-deployment.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-commander"
        c_by_name = get_containers_by_name(doc)
        assert len(c_by_name) == 1
        assert c_by_name["commander"]["image"].startswith(
            "quay.io/astronomer/ap-commander:"
        )

        env_vars = {x["name"]: x["value"] for x in c_by_name["commander"]["env"]}
        assert env_vars["COMMANDER_UPGRADE_TIMEOUT"] == "600"

    def test_astronomer_commander_rbac_cluster_role_enabled(self, kube_version):
        """Test that if rbacEnabled and clusterRoles are enabled but
        namespacePools disabled, helm renders ClusterRole and
        ClusterRoleBinding resources."""

        # First rbacEnabled and clusterRoles set to true and namespacePools disabled, should create a ClusterRole and ClusterRoleBinding
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "rbacEnabled": True,
                    "clusterRoles": True,
                    "features": {
                        "namespacePools": {"enabled": False},
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/commander/commander-role.yaml",
                "charts/astronomer/templates/commander/commander-rolebinding.yaml",
            ],
        )

        cluster_role = docs[0]

        assert cluster_role["kind"] == "ClusterRole"
        assert len(cluster_role["rules"]) > 0

        cluster_role_binding = docs[1]

        expected_role_ref = {
            "kind": "ClusterRole",
            "apiGroup": "rbac.authorization.k8s.io",
            "name": "release-name-commander",
        }
        expected_subjects = [
            {
                "kind": "ServiceAccount",
                "name": "release-name-commander",
                "namespace": "default",
            }
        ]
        assert cluster_role_binding["kind"] == "ClusterRoleBinding"
        assert cluster_role_binding["roleRef"] == expected_role_ref
        assert cluster_role_binding["subjects"] == expected_subjects

    def test_astronomer_commander_rbac_cluster_roles_disabled_rbac_enabled(
        self, kube_version
    ):
        """Test that if rbacEnabled set to true, but clusterRoles and
        namespacePools are disabled, we do not create any RBAC resources."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "clusterRoles": True,
                    "rbacEnabled": False,
                    "features": {
                        "namespacePools": {"enabled": False},
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/commander/commander-role.yaml",
                "charts/astronomer/templates/commander/commander-rolebinding.yaml",
            ],
        )
        assert len(docs) == 0

    def test_astronomer_commander_rbac_all_disabled(self, kube_version):
        """Test that if rbacEnabled, namespacePools and clusterRoles are
        disabled, we do not create any RBAC resources."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "clusterRoles": False,
                    "rbacEnabled": False,
                    "features": {
                        "namespacePools": {"enabled": False},
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/commander/commander-role.yaml",
                "charts/astronomer/templates/commander/commander-rolebinding.yaml",
            ],
        )
        assert len(docs) == 0
