import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


def get_env_value(env_var):
    """Helper function to get the value of an environment variable."""
    if "value" in env_var:
        return env_var["value"]
    if "valueFrom" in env_var:
        return env_var["valueFrom"]
    return None


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerCommander:
    def test_astronomer_commander_deployment_default(self, kube_version):
        """Test that helm renders a good deployment template for
        astronomer/commander."""
        values = {
            "astronomer": {
                "airflowChartVersion": "99.88.77",
                "commander": {
                    "cloudProvider": "aws",
                    "region": "us-west-2",
                    "houstonAuthorizationUrl": "https://houston.example.com/auth",
                },
                "images": {"commander": {"tag": "88.77.66"}},
            },
            "global": {"baseDomain": "astronomer.example.com", "plane": {"mode": "data", "domainSuffix": "custom-dp-123"}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-commander"
        c_by_name = get_containers_by_name(doc)
        assert len(c_by_name) == 1
        assert c_by_name["commander"]["image"].startswith("quay.io/astronomer/ap-commander:")
        assert c_by_name["commander"]["resources"]["limits"]["memory"] == "2Gi"
        assert c_by_name["commander"]["resources"]["requests"]["memory"] == "1Gi"
        env_vars = {x["name"]: get_env_value(x) for x in c_by_name["commander"]["env"]}
        assert env_vars["COMMANDER_UPGRADE_TIMEOUT"] == "600"
        assert "COMMANDER_MANAGE_NAMESPACE_RESOURCE" not in env_vars

        assert env_vars["COMMANDER_ELASTICSEARCH_ENABLED"] == "true"
        assert env_vars["COMMANDER_ELASTICSEARCH_LOG_LEVEL"] == "info"
        assert env_vars["COMMANDER_ELASTICSEARCH_NODE"] == "https://elasticsearch.custom-dp-123.example.com"
        assert env_vars["COMMANDER_HEALTH_STATUS"] == "HEALTHY"
        assert env_vars["COMMANDER_STATUS"] == "HEALTHY"
        assert env_vars["COMMANDER_AIRFLOW_CHART_VERSION"] == "99.88.77"
        assert env_vars["COMMANDER_DATAPLANE_CHART_VERSION"] != ""
        assert env_vars["COMMANDER_CLOUD_PROVIDER"] == "aws"
        assert env_vars["COMMANDER_VERSION"] == "88.77.66"
        assert "COMMANDER_DATAPLANE_DATABASE_URL" in env_vars
        assert env_vars["COMMANDER_DATAPLANE_ID"] == "custom-dp-123"
        assert env_vars["COMMANDER_REGION"] == "us-west-2"
        assert env_vars["COMMANDER_BASE_DOMAIN"] == "custom-dp-123.example.com"
        assert env_vars["COMMANDER_DATAPLANE_URL"] == "custom-dp-123.example.com"
        assert env_vars["COMMANDER_DATAPLANE_MODE"] == "data"
        assert env_vars["COMMANDER_HOUSTON_JWKS_ENDPOINT"] == "https://houston.example.com"

    def test_astronomer_commander_deployment_upgrade_timeout(self, kube_version):
        """Test that helm renders a good deployment template for
        astronomer/commander.

        when upgrade timeout is set
        """
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"commander": {"upgradeTimeout": 997}}},
            show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-commander"
        c_by_name = get_containers_by_name(doc)
        assert len(c_by_name) == 1
        assert c_by_name["commander"]["image"].startswith("quay.io/astronomer/ap-commander:")

        env_vars = {x["name"]: get_env_value(x) for x in c_by_name["commander"]["env"]}
        assert env_vars["COMMANDER_UPGRADE_TIMEOUT"] == "997"

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

    def test_astronomer_commander_rbac_cluster_roles_disabled_rbac_enabled(self, kube_version):
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

    def test_astronomer_commander_rbac_cluster_role_disabled(self, kube_version):
        """Test that if clusterRoles and namespacePools are disabled but
        rbacEnabled is enabled, helm does not render RBAC resources."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "clusterRoles": False,
                    "rbacEnabled": True,
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

    def test_astronomer_commander_rbac_multinamespace_mode_disabled(self, kube_version):
        """Test that if Houston's Airflow chart sub-configuration has
        multiNamespaceMode disabled, the rendered commander role doesn't have
        permissions to manage Cluster-level RBAC resources."""
        doc = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"config": {"deployments": {"helm": {"airflow": {"multiNamespaceMode": False}}}}}}},
            show_only=["charts/astronomer/templates/commander/commander-role.yaml"],
        )[0]

        cluster_resources = ["clusterrolebindings", "clusterroles"]

        # check that there is no rules regarding ClusterRoles and ClusterRolesBinding
        generated_resources = [resource for rule in doc["rules"] if "resources" in rule for resource in rule["resources"]]
        for resource in generated_resources:
            assert resource not in cluster_resources

    def test_astronomer_commander_rbac_multinamespace_mode_undefined(self, kube_version):
        """Test that if Houston's configuration for Airflow chart is not
        defined, the rendered commander role doesn't have permissions to manage
        Cluster-level RBAC resources."""
        doc = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/astronomer/templates/commander/commander-role.yaml"],
        )[0]

        cluster_resources = ["clusterrolebindings", "clusterroles"]

        # check that there is no rules regarding ClusterRoles and ClusterRolesBinding
        generated_resources = [resource for rule in doc["rules"] if "resources" in rule for resource in rule["resources"]]
        for resource in generated_resources:
            assert resource not in cluster_resources

    def test_astronomer_commander_rbac_multinamespace_mode_enabled(self, kube_version):
        """Test that if Houston's Airflow chart sub-configuration has
        multiNamespaceMode enabled, the rendered commander role has permissions
        to manage Cluster-level RBAC resources."""
        doc = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"config": {"deployments": {"helm": {"airflow": {"multiNamespaceMode": True}}}}}}},
            show_only=["charts/astronomer/templates/commander/commander-role.yaml"],
        )[0]

        cluster_resources = ["clusterrolebindings", "clusterroles"]

        # check that there are rules for cluterroles and clusterrolebindings
        generated_resources = [resource for rule in doc["rules"] if "resources" in rule for resource in rule["resources"]]
        for resource in cluster_resources:
            assert resource in generated_resources

    def test_astronomer_commander_rbac_scc_enabled_ns_pools(self, kube_version):
        """Test that if a sccEnabled and namespacePools are enabled, we add
        Cluster permissions for scc resources."""
        namespaces = ["test"]
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "rbacEnabled": True,
                    "sccEnabled": True,
                    "features": {
                        "namespacePools": {
                            "enabled": True,
                            "namespaces": {"create": True, "names": namespaces},
                        },
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/commander/commander-role.yaml",
                "charts/astronomer/templates/commander/commander-rolebinding.yaml",
            ],
        )

        assert len(docs) == 6

        expected_namespaces = [*namespaces, "default"]

        cluster_role = docs[0]
        expected_rule = {
            "apiGroups": ["security.openshift.io"],
            "resources": ["securitycontextconstraints"],
            "verbs": ["create", "delete", "get", "patch", "list", "watch"],
        }
        assert cluster_role["kind"] == "ClusterRole"
        assert cluster_role["rules"] == [expected_rule]

        # assertions on Role objects
        for i in range(1, 3):
            role = docs[i]

            assert role["kind"] == "Role"
            assert len(role["rules"]) > 0
            assert role["metadata"]["namespace"] == expected_namespaces[i - 1]

        # Role Bindings
        expected_subject = {
            "kind": "ServiceAccount",
            "name": "release-name-commander",
            "namespace": "default",
        }

        cluster_role_binding = docs[3]
        expected_scc_cluster_role = {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": "release-name-commander-scc",
        }

        assert cluster_role_binding["roleRef"] == expected_scc_cluster_role

        for i in range(4, 6):
            role_binding = docs[i]

            expected_role = {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": "release-name-commander",
            }

            assert role_binding["kind"] == "RoleBinding"
            assert role_binding["metadata"]["namespace"] == expected_namespaces[i - 4]
            assert role_binding["roleRef"] == expected_role
            assert role_binding["subjects"][0] == expected_subject

    def test_astronomer_commander_rbac_scc_cluster_roles(self, kube_version):
        """Test that if scc is enabled but namespace pools is disabled, scc
        permissions are rendered once in ClusterRole and ClusterRoleBinding
        objects."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "rbacEnabled": True,
                    "sccEnabled": True,
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

        assert len(docs) == 2

        expected_rule = {
            "apiGroups": ["security.openshift.io"],
            "resources": ["securitycontextconstraints"],
            "verbs": ["create", "delete", "get", "patch", "list", "watch"],
        }
        cluster_role = docs[0]

        assert cluster_role["kind"] == "ClusterRole"
        assert expected_rule in cluster_role["rules"]

        cluster_role_binding = docs[1]
        expected_cluster_role = {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": "release-name-commander",
        }

        assert cluster_role_binding["roleRef"] == expected_cluster_role

    def test_astronomer_commander_disable_manage_clusterscopedresources_overrides(self, kube_version):
        """Test that helm renders a good deployment template for
        astronomer/commander."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"disableManageClusterScopedResources": True}},
            show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-commander"
        c_by_name = get_containers_by_name(doc)
        env_vars = {x["name"]: get_env_value(x) for x in c_by_name["commander"]["env"]}
        assert env_vars["COMMANDER_MANAGE_NAMESPACE_RESOURCE"] == "false"

    def test_astronomer_commander_clusterscopedresources_overrides_with_custom_flags(self, kube_version):
        """Test that helm renders a good deployment template for
        astronomer/commander."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "disableManageClusterScopedResources": True,
                    "features": {"namespacePools": {"enabled": True}},
                },
                "astronomer": {
                    "commander": {
                        "env": [{"name": "COMMANDER_HELM_DEBUG", "value": "true"}],
                        "airGapped": {"enabled": True},
                    }
                },
            },
            show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-commander"
        c_by_name = get_containers_by_name(doc)
        env_vars = {x["name"]: get_env_value(x) for x in c_by_name["commander"]["env"]}
        assert env_vars["COMMANDER_HELM_DEBUG"] == "true"
        assert env_vars["COMMANDER_MANAGE_NAMESPACE_RESOURCE"] == "false"
        assert env_vars["COMMANDER_MANUAL_NAMESPACE_NAMES"] == "true"
        assert env_vars["COMMANDER_AIRGAPPED"] == "true"

    def test_astronomer_commander_operator_permissions(self, kube_version):
        """Test template that helm renders when operator is enabled ."""
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "airflowOperator": {"enabled": True},
                },
            },
            show_only=["charts/astronomer/templates/commander/commander-role.yaml"],
        )[0]
        expected_rule = {
            "apiGroups": ["airflow.apache.org"],
            "resources": ["airflows"],
            "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"],
        }
        assert any(rule == expected_rule for rule in doc["rules"])

    def test_astronomer_commander_operator_permissions_disabled(self, kube_version):
        """Test template that helm renders when operator is enabled ."""
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "airflowOperator": {"enabled": False},
                },
            },
            show_only=["charts/astronomer/templates/commander/commander-role.yaml"],
        )[0]
        expected_rule = {
            "apiGroups": ["airflow.apache.org"],
            "resources": ["airflows"],
            "verbs": ["get", "list", "watch", "create", "update", "patch", "delete"],
        }
        assert not any(rule == expected_rule for rule in doc["rules"])

    @pytest.mark.parametrize(
        "mode,custom_logging,expected_node",
        [
            (
                "data",
                False,
                "https://elasticsearch.custom-dp-123.example.com",
            ),
            (
                "unified",
                True,
                "http://release-name-es-proxy.default.svc.cluster.local:9201",
            ),
            (
                "unified",
                False,
                "http://release-name-elasticsearch.default.svc.cluster.local.:9200",
            ),
        ],
    )
    def test_commander_elasticsearch_node_variants(self, kube_version, mode, custom_logging, expected_node):
        """Test COMMANDER_ELASTICSEARCH_NODE is rendered correctly for different
        plane modes and custom logging configurations."""
        values = {
            "astronomer": {
                "images": {"commander": {"tag": "1.2.3"}},
            },
            "global": {
                "baseDomain": "astronomer.example.com",
                "plane": {"mode": mode, "domainSuffix": "custom-dp-123"},
                "customLogging": {"enabled": custom_logging},
            },
        }

        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        env_vars = {x["name"]: get_env_value(x) for x in c_by_name["commander"]["env"]}

        assert env_vars["COMMANDER_ELASTICSEARCH_NODE"] == expected_node
