import jmespath
import pytest

from tests import supported_k8s_versions
from tests.utils import get_env_vars_dict
from tests.utils.chart import render_chart


def get_containers_by_name(doc):
    """Helper function to get containers by name from a deployment."""
    containers = doc["spec"]["template"]["spec"]["containers"]
    return {container["name"]: container for container in containers}


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
        assert "var-cache-nginx" in volume_mounts
        assert volume_mounts["var-cache-nginx"] == "/var/run"

        volumes = {vol["name"]: vol for vol in doc["spec"]["template"]["spec"]["volumes"]}
        assert "tmp" in volumes
        assert "emptyDir" in volumes["tmp"]
        assert "var-cache-nginx" in volumes
        assert "emptyDir" in volumes["var-cache-nginx"]

    def test_astro_ui_extra_volume_mounts(self, kube_version):
        """Test that user-provided volumeMounts and extraVolumes are rendered with correct indentation."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "astroUI": {
                        "env": [
                            {
                                "name": "NODE_EXTRA_CA_CERTS",
                                "value": "/usr/local/share/ca-certificates/ldap-ca.crt",
                            }
                        ],
                        "volumeMounts": [
                            {
                                "name": "ldap-ca",
                                "mountPath": "/usr/local/share/ca-certificates/ldap-ca.crt",
                                "subPath": "ldap-ca.crt",
                                "readOnly": True,
                            }
                        ],
                        "extraVolumes": [
                            {
                                "name": "ldap-ca",
                                "secret": {
                                    "secretName": "houston-ldap-tls",
                                    "items": [{"key": "ca.crt", "path": "ldap-ca.crt"}],
                                },
                            }
                        ],
                    }
                }
            },
            show_only=["charts/astronomer/templates/astro-ui/astro-ui-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        astro_ui_container = get_containers_by_name(doc)["astro-ui"]

        volume_mounts = {mount["name"]: mount for mount in astro_ui_container["volumeMounts"]}
        assert "ldap-ca" in volume_mounts
        assert volume_mounts["ldap-ca"]["mountPath"] == "/usr/local/share/ca-certificates/ldap-ca.crt"
        assert volume_mounts["ldap-ca"]["subPath"] == "ldap-ca.crt"
        assert volume_mounts["ldap-ca"]["readOnly"] is True

        volumes = {vol["name"]: vol for vol in doc["spec"]["template"]["spec"]["volumes"]}
        assert "ldap-ca" in volumes
        assert volumes["ldap-ca"]["secret"]["secretName"] == "houston-ldap-tls"

    def test_astro_ui_user_provided_env_vars(self, kube_version):
        """Test that user-provided env vars are injected into the astro-ui container."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "astroUI": {
                        "env": [
                            {"name": "MY_CUSTOM_VAR", "value": "custom-value"},
                            {"name": "ANOTHER_VAR", "value": "another-value"},
                        ],
                    }
                }
            },
            show_only=["charts/astronomer/templates/astro-ui/astro-ui-deployment.yaml"],
        )
        assert len(docs) == 1
        astro_ui_container = get_containers_by_name(docs[0])["astro-ui"]
        env_vars = get_env_vars_dict(astro_ui_container["env"])
        assert env_vars["MY_CUSTOM_VAR"] == "custom-value"
        assert env_vars["ANOTHER_VAR"] == "another-value"
