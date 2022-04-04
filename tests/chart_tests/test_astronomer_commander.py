from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import jmespath


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_commander_deployment(kube_version):
    """Test that helm renders a good deployment template for astronomer/commander."""
    docs = render_chart(
        kube_version=kube_version,
        show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "Deployment"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == "release-name-commander"
    assert any(
        image_name.startswith("quay.io/astronomer/ap-commander:")
        for image_name in jmespath.search("spec.template.spec.containers[*].image", doc)
    )
    assert len(doc["spec"]["template"]["spec"]["containers"]) == 1
    env_vars = {
        x["name"]: x["value"]
        for x in doc["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert env_vars["COMMANDER_UPGRADE_TIMEOUT"] == "300"


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_commander_deployment_upgrade_timeout(kube_version):
    """Test that helm renders a good deployment template for astronomer/commander. when upgrade timeout is set"""
    docs = render_chart(
        kube_version=kube_version,
        values={"astronomer": {"commander": {"upgradeTimeout": 600}}},
        show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "Deployment"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == "release-name-commander"
    assert any(
        image_name.startswith("quay.io/astronomer/ap-commander:")
        for image_name in jmespath.search("spec.template.spec.containers[*].image", doc)
    )

    assert len(doc["spec"]["template"]["spec"]["containers"]) == 1
    env_vars = {
        x["name"]: x["value"]
        for x in doc["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert env_vars["COMMANDER_UPGRADE_TIMEOUT"] == "600"


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_commander_rbac_cluster_role_enabled(kube_version):
    """Test that if rbacEnabled and clusterRoles are enabled but namespacePools disabled, helm renders ClusterRole and ClusterRoleBinding resources"""

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


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_commander_rbac_cluster_roles_disabled_rbac_enabled(kube_version):
    """Test that if rbacEnabled set to true, but clusterRoles and namespacePools are disabled, we do not create any RBAC resources"""
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


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_commander_rbac_all_disabled(kube_version):
    """Test that if rbacEnabled, namespacePools and clusterRoles are disabled, we do not create any RBAC resources"""
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


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_commander_rbac_cluster_role_disabled(kube_version):
    """Test that if clusterRoles and namespacePools are disabled but rbacEnabled is enabled, helm does not render RBAC resources"""
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


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_commander_rbac_multinamespace_mode_disabled(kube_version):
    """Test that if Houston's Airflow chart sub-configuration has multiNamespaceMode disabled, the rendered commander role doesn't have permissions to manage Cluster-level RBAC resources"""
    doc = render_chart(
        kube_version=kube_version,
        values={
            "astronomer": {
                "houston": {
                    "config": {
                        "deployments": {
                            "helm": {"airflow": {"multiNamespaceMode": False}}
                        }
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/commander/commander-role.yaml"],
    )[0]

    cluster_resources = ["clusterrolebindings", "clusterroles"]

    # check that there is no rules regarding ClusterRoles and ClusterRolesBinding
    generated_resources = [
        resource
        for rule in doc["rules"]
        if "resources" in rule
        for resource in rule["resources"]
    ]
    for resource in generated_resources:
        assert resource not in cluster_resources


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_commander_rbac_multinamespace_mode_undefined(kube_version):
    """Test that if Houston's configuration for Airflow chart is not defined, the rendered commander role doesn't have permissions to manage Cluster-level RBAC resources"""
    doc = render_chart(
        kube_version=kube_version,
        values={},
        show_only=["charts/astronomer/templates/commander/commander-role.yaml"],
    )[0]

    cluster_resources = ["clusterrolebindings", "clusterroles"]

    # check that there is no rules regarding ClusterRoles and ClusterRolesBinding
    generated_resources = [
        resource
        for rule in doc["rules"]
        if "resources" in rule
        for resource in rule["resources"]
    ]
    for resource in generated_resources:
        assert resource not in cluster_resources


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_commander_rbac_multinamespace_mode_enabled(kube_version):
    """Test that if Houston's Airflow chart sub-configuration has multiNamespaceMode enabled, the rendered commander role has permissions to manage Cluster-level RBAC resources"""
    doc = render_chart(
        kube_version=kube_version,
        values={
            "astronomer": {
                "houston": {
                    "config": {
                        "deployments": {
                            "helm": {"airflow": {"multiNamespaceMode": True}}
                        }
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/commander/commander-role.yaml"],
    )[0]

    cluster_resources = ["clusterrolebindings", "clusterroles"]

    # check that there are rules for cluterroles and clusterrolebindings
    generated_resources = [
        resource
        for rule in doc["rules"]
        if "resources" in rule
        for resource in rule["resources"]
    ]
    for resource in cluster_resources:
        assert resource in generated_resources
