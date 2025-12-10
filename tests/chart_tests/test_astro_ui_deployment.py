import jmespath
import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


def get_containers_by_name(doc):
    """Helper function to get containers by name from a deployment."""
    containers = doc["spec"]["template"]["spec"]["containers"]
    return {container["name"]: container for container in containers}


def get_env_value(env_var):
    """Helper function to get environment variable value."""
    if "value" in env_var:
        return env_var["value"]
    return None


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstroUIDeployment:
    def test_astro_ui_deployment(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "astroUI": {
                        "resources": {
                            "requests": {"cpu": "100m", "memory": "256Mi"},
                            "limits": {"cpu": "500m", "memory": "1024Mi"},
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/astro-ui/astro-ui-deployment.yaml"],
        )

        assert "Deployment" == jmespath.search("kind", docs[0])
        assert "release-name-astro-ui" == jmespath.search("metadata.name", docs[0])
        assert "astro-ui" == jmespath.search("spec.template.spec.containers[0].name", docs[0])
        assert "500m" == jmespath.search("spec.template.spec.containers[0].resources.limits.cpu", docs[0])

    def test_astro_ui_deployment_volumes(self, kube_version):
        """Test that astro-ui deployment has correct volumes and volume mounts."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "astroUI": {
                        "resources": {
                            "requests": {"cpu": "100m", "memory": "256Mi"},
                            "limits": {"cpu": "500m", "memory": "1024Mi"},
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/astro-ui/astro-ui-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc)
        assert "astro-ui" in c_by_name

        astro_ui_container = c_by_name["astro-ui"]

        volume_mounts = {mount["name"]: mount["mountPath"] for mount in astro_ui_container["volumeMounts"]}
        assert "tmp" in volume_mounts
        assert volume_mounts["tmp"] == "/tmp"
        assert "var-run" in volume_mounts
        assert volume_mounts["var-cache-nginx"] == "/var/run"

        volumes = {vol["name"]: vol for vol in doc["spec"]["template"]["spec"]["volumes"]}
        assert "tmp" in volumes
        assert "emptyDir" in volumes["tmp"]
        assert "var-cache-nginx" in volumes
        assert "emptyDir" in volumes["var-cache-nginx"]
