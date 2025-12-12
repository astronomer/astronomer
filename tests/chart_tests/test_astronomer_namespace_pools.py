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
    def test_namespace_pools_rbac(self, kube_version):
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

    @pytest.mark.parametrize(
        "namespace_labels", [{}, {"foo": "FOO", "bar": "BAR"}], ids=["empty-namespaceLabels", "with-namespaceLabels"]
    )
    def test_namespaces_namespace_pools_enabled_create_true(self, kube_version, namespace_labels):
        """Test that namespaces resources are rendered properly when namespacePools feature is enabled."""
        namespaces = ["my-namespace-1", "my-namespace-2"]
        values = {
            "global": {
                "features": {
                    "namespacePools": {
                        "enabled": True,
                        "namespaces": {"create": True, "names": namespaces},
                    }
                },
            }
        }
        if namespace_labels:
            values["global"]["namespaceLabels"] = namespace_labels

        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/astronomer/templates/namespaces.yaml",
                "charts/astronomer/templates/commander/commander-metadata.yaml",
            ],
        )

        assert len(docs) == 3
        commander_metadata_yaml = yaml.safe_load(docs[2]["data"]["metadata.yaml"])
        for i, doc in enumerate(docs[:2]):
            assert doc["metadata"]["name"] == namespaces[i]
            assert doc["kind"] == "Namespace"
            if namespace_labels:
                assert doc["metadata"]["labels"] == namespace_labels
                assert commander_metadata_yaml["namespaceLabels"] == namespace_labels
            else:
                assert not doc["metadata"].get("labels")
                assert commander_metadata_yaml["namespaceLabels"] == {}

    def test_namespaces_namespace_pools_disabled_create_true(self, kube_version):
        """Test that no namespaces resources are rendered when namespacePools feature is disabled."""
        namespaces = ["my-namespace-1", "my-namespace-2"]
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
            show_only=[
                "charts/astronomer/templates/namespaces.yaml",
                "charts/astronomer/templates/commander/commander-metadata.yaml",
            ],
        )
        assert len(docs) == 1
        commander_metadata_yaml = yaml.safe_load(docs[0]["data"]["metadata.yaml"])
        assert commander_metadata_yaml["namespaceLabels"] == {}

    def test_namespaces_namespace_pools_enabled_create_false(self, kube_version):
        """Test that no namespaces resources are rendered when namespacePools feature is enabled but namespaces creation is disabled."""
        namespaces = ["my-namespace-1", "my-namespace-2"]
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
            show_only=[
                "charts/astronomer/templates/namespaces.yaml",
                "charts/astronomer/templates/commander/commander-metadata.yaml",
            ],
        )
        assert len(docs) == 1
        commander_metadata_yaml = yaml.safe_load(docs[0]["data"]["metadata.yaml"])
        assert commander_metadata_yaml["namespaceLabels"] == {}

    def test_commander_deployment_namespace_pools_enabled_create_false(self, kube_version):
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

    def test_commander_deployment_namespace_pools_disabled_create_true(self, kube_version):
        """Test that commander deployment is configured properly when disabling namespace pools."""
        namespaces = ["my-namespace-1", "my-namespace-2"]
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

    def test_houston_configmap_namespace_pools_enabled_create_true(self, kube_version):
        """Test that Houston production.yaml configuration parameters are configured properly when namespacePools is enabled."""
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

    def test_houston_configmap_namespace_pools_disabled_create_true(self, kube_version):
        """Test that Houston production.yaml configuration parameters are configured properly when namespacePools is disabled."""
        namespaces = ["my-namespace-1", "my-namespace-2"]
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

    def test_namespace_pools_enabled_create_rbac_false(self, kube_version):
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

    def test_namespace_pools_vector_configmap(self, kube_version):
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
