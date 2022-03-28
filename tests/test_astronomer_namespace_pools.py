from tests.helm_template_generator import render_chart
import pytest
import yaml
from . import supported_k8s_versions, get_containers_by_name


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_namespace_pools_rbac(kube_version):
    """Test that helm renders astronomer/commander RBAC resources properly when working with namespace pools"""

    # rbacEnabled and clusterRoles and namespacePools set to true, should create Roles and Rolebindings for namespace in Pool
    # and ignore the cluster role configuration
    namespaces = ["my-namespace-1", "my-namespace-2"]
    docs = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "rbacEnabled": True,
                "clusterRoles": True,
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

    assert len(docs) == 4

    # assertions on Role objects
    for i in range(0, 2):
        role = docs[i]

        assert role["kind"] == "Role"
        assert len(role["rules"]) > 0
        assert role["metadata"]["namespace"] == namespaces[i]

    for i in range(2, 4):
        role_binding = docs[i]

        expected_subject = {
            "kind": "ServiceAccount",
            "name": "release-name-commander",
            "namespace": "default",
        }
        expected_role = {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": "release-name-commander",
        }

        assert role_binding["kind"] == "RoleBinding"
        assert role_binding["metadata"]["namespace"] == namespaces[i - 2]
        assert role_binding["roleRef"] == expected_role
        assert role_binding["subjects"][0] == expected_subject


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_namespace_pools_namespaces(kube_version):
    """Test that Namespaces resources are rendered properly when using namespacePools feature"""
    # If namespace Pools creation enabled -> create the namespaces
    namespaces = ["my-namespace-1", "my-namespace-2"]
    docs = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "features": {
                    "namespacePools": {
                        "enabled": True,
                        "namespaces": {"create": True, "names": namespaces},
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/namespaces.yaml"],
    )

    assert len(docs) == 2
    for i in range(0, 2):
        namespace = docs[i]
        assert namespace["metadata"]["name"] == namespaces[i]
        assert namespace["kind"] == "Namespace"

    # If namespace Pools disabled -> should not create the namespaces
    docs = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "features": {
                    "namespacePools": {
                        "enabled": False,
                        "namespaces": {"create": True, "names": namespaces},
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/namespaces.yaml"],
    )
    assert len(docs) == 0

    # If namespace pools enabled but namespaces creation disabled -> should not create the namespaces
    docs = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "features": {
                    "namespacePools": {
                        "enabled": True,
                        "namespaces": {"create": False, "names": namespaces},
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/namespaces.yaml"],
    )
    assert len(docs) == 0


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_namespace_pools_commander_deployment_configuration(kube_version):
    """Test that commander deployment is configured properly when enabling namespace pools"""

    namespaces = ["my-namespace-1", "my-namespace-2"]
    doc = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "features": {
                    "namespacePools": {
                        "enabled": True,
                        "namespaces": {"create": True, "names": namespaces},
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
    )[0]

    # Check that by enabling global.features.namespacePools, the environment variable COMMANDER_MANUAL_NAMESPACE_NAMES
    # is configured properly
    c_by_name = get_containers_by_name(doc, include_init_containers=False)

    manual_ns_env_found = False
    for env in c_by_name["commander"]["env"]:
        if env["name"] == "COMMANDER_MANUAL_NAMESPACE_NAMES" and env["value"] == "true":
            manual_ns_env_found = True

    assert manual_ns_env_found

    # If namespacePools is disabled, we should not add the Manual Namespace Names environment variable in commander
    doc = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "features": {
                    "namespacePools": {
                        "enabled": False,
                        "namespaces": {"create": True, "names": namespaces},
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
    )[0]

    # Check that by enabling global.features.namespacePools, the environment variable COMMANDER_MANUAL_NAMESPACE_NAMES
    # is configured properly
    c_by_name = get_containers_by_name(doc, include_init_containers=False)

    manual_ns_env_found = False
    for env in c_by_name["commander"]["env"]:
        if env["name"] == "COMMANDER_MANUAL_NAMESPACE_NAMES" and env["value"] == "true":
            manual_ns_env_found = True

    assert not manual_ns_env_found


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_namespace_pools_houston_configmap(kube_version):
    """Test that Houston production.yaml configuration parameters are configured properly when using namespacePools feature"""
    namespaces = ["my-namespace-1", "my-namespace-2"]
    doc = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "features": {
                    "namespacePools": {
                        "enabled": True,
                        "namespaces": {"create": True, "names": namespaces},
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )[0]

    deployments_config = yaml.safe_load(doc["data"]["production.yaml"])

    assert deployments_config["deployments"]["hardDeleteDeployment"]
    assert deployments_config["deployments"]["manualNamespaceNames"]
    assert deployments_config["deployments"]["preCreatedNamespaces"] == namespaces

    # test configuration when namespacePools is disabled -> should not add configuration parameters
    doc = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "features": {
                    "namespacePools": {
                        "enabled": False,
                        "namespaces": {"create": True, "names": namespaces},
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
    )[0]

    deployments_config = yaml.safe_load(doc["data"]["production.yaml"])

    assert "hardDeleteDeployment" not in deployments_config["deployments"]
    assert "manualNamespaceNames" not in deployments_config["deployments"]
    assert "preCreatedNamespaces" not in deployments_config["deployments"]

@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_astronomer_namespace_pools_fluentd_configmap(kube_version):
    """Test that when namespace Pools is enabled, and a list of namespaces is provided, helm render fluentd configmap correctly, with a regex targeting pods in the provided namespaces only."""
    namespaces = ["my-namespace-1", "my-namespace-2"]
    doc = render_chart(
        kube_version=kube_version,
        values={
            "global": {
                "features": {
                    "namespacePools": {
                        "enabled": True,
                        "namespaces": {"create": True, "names": namespaces},
                    }
                }
            }
        },
        show_only=["charts/fluentd/templates/fluentd-configmap.yaml"],
    )[0]

    expected_rule = "key $.kubernetes.namespace_name\n    pattern ^({}|{})$".format(namespaces[0], namespaces[1])
    assert expected_rule in doc["data"]["output.conf"]