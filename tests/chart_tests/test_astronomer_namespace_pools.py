import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerNamespacePools:
    def test_astronomer_namespace_pools_rbac(self, kube_version):
        """Test that helm renders astronomer/commander RBAC resources properly when working with namespace pools."""

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

        assert len(docs) == 6

        expected_namespaces = [*namespaces, "default"]

        roles = docs[:3]
        for i, doc in enumerate(roles):
            assert doc["kind"] == "Role"
            assert len(doc["rules"]) > 0
            assert doc["metadata"]["namespace"] == expected_namespaces[i]

        role_bindings = docs[3:]
        for i, doc in enumerate(role_bindings):
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

            assert doc["kind"] == "RoleBinding"
            assert doc["metadata"]["namespace"] == expected_namespaces[i]
            assert doc["roleRef"] == expected_role
            assert doc["subjects"][0] == expected_subject

    def test_astronomer_namespace_pools_namespaces(self, kube_version):
        """Test that Namespaces resources are rendered properly when using namespacePools feature."""
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
        for i, doc in enumerate(docs):
            assert doc["metadata"]["name"] == namespaces[i]
            assert doc["kind"] == "Namespace"

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

    def test_astronomer_namespace_pools_commander_deployment_configuration(self, kube_version):
        """Test that commander deployment is configured properly when enabling namespace pools."""

        namespaces = ["my-namespace-1", "my-namespace-2"]
        doc = render_chart(
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
            show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
        )[0]

        # Check that by enabling global.features.namespacePools, the environment variable COMMANDER_MANUAL_NAMESPACE_NAMES
        # is configured properly
        c_by_name = get_containers_by_name(doc, include_init_containers=False)

        commander_env = get_env_vars_dict(c_by_name["commander"]["env"])
        assert commander_env.get("COMMANDER_MANUAL_NAMESPACE_NAMES") == "true"

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

        commander_env = get_env_vars_dict(c_by_name["commander"]["env"])
        assert commander_env.get("COMMANDER_MANUAL_NAMESPACE_NAMES") != "true"

    def test_astronomer_namespace_pools_houston_configmap(self, kube_version):
        """Test that Houston production.yaml configuration parameters are configured properly when using namespacePools feature."""
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
        assert deployments_config["deployments"]["preCreatedNamespaces"] == [{"name": namespace} for namespace in namespaces]
        assert "disableManageClusterScopedResources" not in deployments_config["deployments"]

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

    def test_astronomer_namespace_pools_create_rbac_mode_is_disabled(self, kube_version):
        """Test that commander deployment rbac is generating roles and role binding on namespace pools mode."""

        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "features": {
                        "namespacePools": {
                            "enabled": True,
                            "createRbac": False,
                        }
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/commander/commander-role.yaml",
                "charts/astronomer/templates/commander/commander-rolebinding.yaml",
                "charts/kube-state/templates/kube-state-rolebinding.yaml",
                "charts/kube-state/templates/kube-state-role.yaml",
                "charts/astronomer/templates/config-syncer/config-syncer-role.yaml",
                "charts/astronomer/templates/config-syncer/config-syncer-rolebinding.yaml",
            ],
        )

        assert len(docs) == 0

    def test_astronomer_namespace_pools_vector_configmap(self, kube_version):
        """Test that when namespace Pools is enabled, vector runs in namespaces only."""
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
                    },
                }
            },
            show_only=["charts/vector/templates/vector-configmap.yaml"],
        )[0]
        expected_filter = f'namespaces = ["{namespaces[0]}", "{namespaces[1]}"]'
        assert expected_filter in doc["data"]["vector-config.yaml"]
