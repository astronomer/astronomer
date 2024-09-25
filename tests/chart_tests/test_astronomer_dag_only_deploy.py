import pytest
import yaml
from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestDagOnlyDeploy:
    def test_dagonlydeploy_with_defaults(self, kube_version):
        """Test dagonlydeploy Service defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        prod = yaml.safe_load(docs[0]["data"]["production.yaml"])
        assert prod["deployments"]["dagOnlyDeployment"] is False

    def test_dagonlydeploy_config_enabled(self, kube_version):
        """Test dagonlydeploy Service defaults."""
        resources = {
            "requests": {"memory": "888Mi", "cpu": "666m"},
            "limits": {"memory": "999Mi", "cpu": "777m"},
        }
        images = "someregistry.io/my-custom-image:my-custom-tag"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "dagOnlyDeployment": {
                        "enabled": True,
                        "repository": images.split(":")[0],
                        "tag": images.split(":")[1],
                        "securityContext": {"fsGroup": 55555},
                        "resources": resources,
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod["deployments"]["dagOnlyDeployment"] is True
        assert prod["deployments"]["dagDeploy"] == {
            "enabled": True,
            "images": {
                "dagServer": {
                    "repository": "someregistry.io/my-custom-image",
                    "tag": "my-custom-tag",
                }
            },
            "securityContext": {"fsGroup": 55555},
            "server": {"resources": resources},
            "client": {"resources": resources},
        }

    def test_dagonlydeploy_config_enabled_with_private_registry(self, kube_version):
        """Test dagonlydeploy with private registry."""
        private_registry = "private-registry.example.com"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        "repository": private_registry,
                    },
                    "dagOnlyDeployment": {
                        "enabled": True,
                    },
                }
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod["deployments"]["dagOnlyDeployment"] is True

        assert prod["deployments"]["dagDeploy"]["images"]["dagServer"]["repository"].startswith(private_registry)

    def test_dagonlydeploy_config_enabled_with_openshift_enabled(self, kube_version):
        """Test dagonlydeploy with openshift enabled to validate fsGroup removal."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "openshiftEnabled": True,
                    "dagOnlyDeployment": {
                        "enabled": True,
                    },
                }
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod["deployments"]["dagOnlyDeployment"] is True

        assert {} == prod["deployments"]["dagDeploy"]["securityContext"]

    def test_dagonlydeploy_config_enabled_with_fsGroup_auto(self, kube_version):
        """Test dagonlydeploy with auto to validate fsGroup removal."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "dagOnlyDeployment": {
                        "enabled": True,
                        "securityContext": {"fsGroup": "auto"},
                    },
                }
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod["deployments"]["dagOnlyDeployment"] is True

        assert {} == prod["deployments"]["dagDeploy"]["securityContext"]

    def test_dagonlydeploy_config_enabled_with_persistence_retain(self, kube_version):
        """Test dagonlydeploy to validate persistence policy retain."""
        persistenceRetain = {
            "persistentVolumeClaimRetentionPolicy": {
                "whenDeleted": "Retain",
                "whenScaled": "Retain",
            }
        }
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "dagOnlyDeployment": {
                        "enabled": True,
                        "persistence": persistenceRetain,
                    },
                },
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod["deployments"]["dagOnlyDeployment"] is True

        assert persistenceRetain == prod["deployments"]["dagDeploy"]["persistence"]

    def test_dagonlydeploy_config_enabled_with_persistence_delete(self, kube_version):
        """Test dagonlydeploy to validate persistence policy delete."""
        persistenceRetain = {
            "persistentVolumeClaimRetentionPolicy": {
                "whenDeleted": "Delete",
                "whenScaled": "Retain",
            }
        }
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "dagOnlyDeployment": {
                        "enabled": True,
                        "persistence": persistenceRetain,
                    },
                },
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod["deployments"]["dagOnlyDeployment"] is True
        assert persistenceRetain == prod["deployments"]["dagDeploy"]["persistence"]
