from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
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
def test_astronomer_commander_rbac(kube_version):
    """Test that helm renders astronomer/commander RBAC resources properly"""

    # First rbacEnabled and clusterRoles set to true, should create a ClusterRole and ClusterRoleBinding
    docs = render_chart(
        kube_version=kube_version,
        values={"global": {"rbacEnabled": True, "clusterRoles": True}},
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

    # If clusterRoles or rbacEnabled set to false, should not create any RBAC resource for commander
    docs = render_chart(
        kube_version=kube_version,
        values={"global": {"clusterRoles": False, "rbacEnabled": True}},
        show_only=[
            "charts/astronomer/templates/commander/commander-role.yaml",
            "charts/astronomer/templates/commander/commander-rolebinding.yaml",
        ],
    )
    assert len(docs) == 0

    docs = render_chart(
        kube_version=kube_version,
        values={"global": {"clusterRoles": True, "rbacEnabled": False}},
        show_only=[
            "charts/astronomer/templates/commander/commander-role.yaml",
            "charts/astronomer/templates/commander/commander-rolebinding.yaml",
        ],
    )
    assert len(docs) == 0

    docs = render_chart(
        kube_version=kube_version,
        values={"global": {"clusterRoles": False, "rbacEnabled": False}},
        show_only=[
            "charts/astronomer/templates/commander/commander-role.yaml",
            "charts/astronomer/templates/commander/commander-rolebinding.yaml",
        ],
    )
    assert len(docs) == 0
