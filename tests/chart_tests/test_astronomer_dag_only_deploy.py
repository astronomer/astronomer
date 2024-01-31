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

        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod["deployments"]["dagOnlyDeployment"] is False

    def test_dagonlydeploy_config_enabled(self, kube_version):
        """Test dagonlydeploy Service defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "dagOnlyDeployment": {
                        "enabled": True,
                        "image": "someregistry.io/my-custom-image:my-custom-tag",
                        "securityContext": {"fsGroup": 50000},
                        "resources": {
                            "requests": {"memory": "386Mi", "cpu": "100m"},
                            "limits": {"memory": "386Mi", "cpu": "100m"},
                        },
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
            "securityContext": {"fsGroup": 50000},
            "resources": {
                "requests": {"memory": "386Mi", "cpu": "100m"},
                "limits": {"memory": "386Mi", "cpu": "100m"},
            },
        }
