import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusFederationAuthDeployment:
    def test_prometheus_federation_auth_deployment_defaults(self, kube_version):
        """Test the default configuration of the Prometheus Federation Auth deployment."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-deployment.yaml"],
        )

        assert len(docs) == 1
        deployment = docs[0]
        assert deployment["kind"] == "Deployment"
        assert deployment["metadata"]["name"].endswith("-federation-auth")
        assert deployment["spec"]["selector"]["matchLabels"] == {
            "component": "prometheus-federation-auth",
            "release": "release-name",
        }

        # Verify pod labels
        pod_labels = deployment["spec"]["template"]["metadata"]["labels"]
        assert pod_labels["tier"] == "monitoring"
        assert pod_labels["component"] == "prometheus-federation-auth"
        assert pod_labels["release"] == "release-name"
        assert pod_labels["plane"] == "data"

        # Verify annotations exist (checksum annotation is required)
        assert "checksum/prom-auth-config" in deployment["spec"]["template"]["metadata"]["annotations"]

        # Verify containers
        c_by_name = get_containers_by_name(deployment)
        assert len(c_by_name) == 1
        federation_auth_container = c_by_name["federation-auth"]

        assert federation_auth_container["securityContext"]["readOnlyRootFilesystem"]

        # Verify container ports
        assert len(federation_auth_container["ports"]) == 1
        assert federation_auth_container["ports"][0]["name"] == "http"

        # Verify environment variables
        container_env = get_env_vars_dict(federation_auth_container["env"])
        assert "REGISTRY_AUTH_TOKEN" in container_env
        assert container_env["REGISTRY_AUTH_TOKEN"]["secretKeyRef"]["key"] == "token"

        # Verify volume mounts
        volume_mounts = {vm["name"]: vm for vm in federation_auth_container["volumeMounts"]}
        assert "config" in volume_mounts
        assert volume_mounts["config"]["mountPath"] == "/etc/nginx/nginx.conf"
        assert volume_mounts["config"]["subPath"] == "nginx.conf"
        assert "var-run" in volume_mounts
        assert volume_mounts["var-run"]["mountPath"] == "/var/run/openresty"
        assert "tmp" in volume_mounts

        # Verify volumes
        volumes = {v["name"]: v for v in deployment["spec"]["template"]["spec"]["volumes"]}
        assert "config" in volumes
        assert volumes["config"]["configMap"]["name"].endswith("-federation-auth-config")
        assert "tmp" in volumes
        assert volumes["tmp"]["emptyDir"] == {}
        assert "var-run" in volumes
        assert volumes["var-run"]["emptyDir"] == {}

    def test_prometheus_federation_auth_deployment_not_created_in_control_mode(self, kube_version):
        """Test that the deployment is not created when plane mode is control."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-deployment.yaml"],
        )

        assert len(docs) == 0

    def test_prometheus_federation_auth_service_account(self, kube_version):
        """Test that the correct service account is used."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-deployment.yaml"],
        )

        assert len(docs) == 1
        deployment = docs[0]
        service_account = deployment["spec"]["template"]["spec"]["serviceAccountName"]
        assert service_account is not None

    def test_prometheus_federation_auth_with_pod_annotations(self, kube_version):
        """Test that global pod annotations are applied."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                    "podAnnotations": {"custom-annotation": "custom-value"},
                }
            },
            show_only=["charts/prometheus/templates/prometheus-federation-auth-deployment.yaml"],
        )

        assert len(docs) == 1
        annotations = docs[0]["spec"]["template"]["metadata"]["annotations"]
        assert annotations["custom-annotation"] == "custom-value"

    def test_prometheus_federation_auth_with_custom_port(self, kube_version):
        """Test that custom auth sidecar port is applied."""
        custom_port = 9090
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                    "authSidecar": {"port": custom_port},
                }
            },
            show_only=["charts/prometheus/templates/prometheus-federation-auth-deployment.yaml"],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        federation_auth_container = c_by_name["federation-auth"]
        assert federation_auth_container["ports"][0]["containerPort"] == custom_port

    def test_prometheus_federation_auth_with_custom_resources(self, kube_version):
        """Test that custom resource requests/limits are applied."""
        custom_resources = {
            "requests": {"cpu": "500m", "memory": "512Mi"},
            "limits": {"cpu": "1000m", "memory": "1Gi"},
        }
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "federation": {"auth": {"resources": custom_resources}},
            },
            show_only=["charts/prometheus/templates/prometheus-federation-auth-deployment.yaml"],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        federation_auth_container = c_by_name["federation-auth"]
        assert federation_auth_container["resources"]["requests"]["cpu"] == "500m"
        assert federation_auth_container["resources"]["limits"]["cpu"] == "1000m"
