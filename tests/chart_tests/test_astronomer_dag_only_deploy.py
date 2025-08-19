import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


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

    def test_dagonlydeploy_with_serviceaccount_overrides(self, kube_version):
        """Test dagonlydeploy Service Account overrides."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"dagOnlyDeployment": {"enabled": True, "serviceAccount": {"create": True}}}},
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        assert len(docs) == 1
        prod = yaml.safe_load(docs[0]["data"]["production.yaml"])
        assert prod["deployments"]["dagOnlyDeployment"] is True
        assert prod["deployments"]["dagDeploy"]["enabled"] is True
        assert "serviceAccount" in prod["deployments"]["dagDeploy"]
        assert {"create": True} == prod["deployments"]["dagDeploy"]["serviceAccount"]

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
                        "securityContexts": {"pod": {"fsGroup": 55555}, "container": {"runAsUser": 12345}},
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
            "securityContexts": {"pod": {"fsGroup": 55555}, "container": {"runAsUser": 12345}},
            "server": {"resources": resources},
            "client": {"resources": resources},
        }

    def test_dagonlydeploy_config_enabled_with_defaults(self, kube_version):
        """Test dagonlydeploy Service defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"dagOnlyDeployment": {"enabled": True}}},
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod["deployments"]["dagOnlyDeployment"] is True
        assert prod["deployments"]["dagDeploy"]["enabled"] is True
        assert "server" not in prod["deployments"]["dagDeploy"]
        assert "client" not in prod["deployments"]["dagDeploy"]

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

        assert {} == prod["deployments"]["dagDeploy"]["securityContexts"]

    def test_dagonlydeploy_config_enabled_with_fsGroup_auto(self, kube_version):
        """Test dagonlydeploy with auto to validate fsGroup removal."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "dagOnlyDeployment": {
                        "enabled": True,
                        "securityContexts": {"pod": {"fsGroup": "auto"}},
                    },
                }
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod["deployments"]["dagOnlyDeployment"] is True

        assert {} == prod["deployments"]["dagDeploy"]["securityContexts"]

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

    def test_houston_configmap_with_dagonlydeployment_probe(self, kube_version):
        """Validate the dagOnlyDeployment liveness and readiness probes in the Houston configmap."""
        images = "someregistry.io/my-custom-image:my-custom-tag"
        liveness_probe = {
            "httpGet": {"path": "/dag-liveness", "port": 8081, "scheme": "HTTP"},
            "initialDelaySeconds": 15,
            "timeoutSeconds": 5,
            "periodSeconds": 10,
            "successThreshold": 1,
            "failureThreshold": 3,
        }
        readiness_probe = {
            "httpGet": {"path": "/dag-readiness", "port": 8081, "scheme": "HTTP"},
            "initialDelaySeconds": 15,
            "timeoutSeconds": 5,
            "periodSeconds": 10,
            "successThreshold": 1,
            "failureThreshold": 3,
        }
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "dagOnlyDeployment": {
                        "enabled": True,
                        "repository": images.split(":")[0],
                        "tag": images.split(":")[1],
                        "server": {"livenessProbe": liveness_probe, "readinessProbe": readiness_probe},
                        "client": {"livenessProbe": liveness_probe, "readinessProbe": readiness_probe},
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod_yaml["deployments"]["dagDeploy"] == {
            "enabled": True,
            "images": {
                "dagServer": {
                    "repository": "someregistry.io/my-custom-image",
                    "tag": "my-custom-tag",
                }
            },
            "securityContexts": {"pod": {"fsGroup": 50000}},
            "server": {"readinessProbe": readiness_probe, "livenessProbe": liveness_probe},
            "client": {"readinessProbe": readiness_probe, "livenessProbe": liveness_probe},
        }

    def test_houston_configmap_with_dagonlydeployment_scheduling(self, kube_version, global_platform_node_pool_config):
        """Validate the dagOnlyDeployment taints, toleration, and node selector in the Houston configmap."""
        images = "someregistry.io/my-custom-image:my-custom-tag"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "dagOnlyDeployment": {
                        "enabled": True,
                        "repository": images.split(":")[0],
                        "tag": images.split(":")[1],
                        "server": {
                            "nodeSelector": global_platform_node_pool_config["nodeSelector"],
                            "affinity": global_platform_node_pool_config["affinity"],
                            "tolerations": global_platform_node_pool_config["tolerations"],
                        },
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod_yaml["deployments"]["dagDeploy"] == {
            "enabled": True,
            "images": {
                "dagServer": {
                    "repository": "someregistry.io/my-custom-image",
                    "tag": "my-custom-tag",
                }
            },
            "securityContexts": {"pod": {"fsGroup": 50000}},
            "server": {
                "nodeSelector": global_platform_node_pool_config["nodeSelector"],
                "affinity": global_platform_node_pool_config["affinity"],
                "tolerations": global_platform_node_pool_config["tolerations"],
            },
        }
