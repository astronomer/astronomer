import pytest

from tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "cluster_roles,expected_kind",
    [(True, "ClusterRole"), (False, "Role")],
)
def test_global_cluster_roles_commander_role(cluster_roles, expected_kind):
    """Test global clusterRoles feature of commander role/rolebinding
    template."""
    docs = render_chart(
        values={"global": {"clusterRoles": cluster_roles}},
        show_only=["charts/astronomer/templates/commander/commander-role.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]

    assert doc["kind"] == expected_kind


@pytest.mark.parametrize(
    "cluster_roles,expected_kind",
    [(True, "ClusterRoleBinding"), (False, "RoleBinding")],
)
def test_global_cluster_roles_commander_rolebinding(cluster_roles, expected_kind):
    """Test global clusterRoles feature of commander role/rolebinding
    template."""
    docs = render_chart(
        values={"global": {"clusterRoles": cluster_roles}},
        show_only=["charts/astronomer/templates/commander/commander-rolebinding.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]

    assert doc["kind"] == expected_kind
