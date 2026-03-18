import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestDpLinkDeployment:
    def test_dp_link_deployment_defaults(self, kube_version):
        """Test the default configuration of the DP-Link deployment."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
        )

        assert len(docs) == 1
        dp_link_deployment = docs[0]
        assert dp_link_deployment["kind"] == "Deployment"
        assert dp_link_deployment["metadata"]["name"] == "release-name-dp-link"

        assert dp_link_deployment["spec"]["replicas"] == 3
        assert dp_link_deployment["spec"]["selector"]["matchLabels"] == {
            "tier": "astronomer",
            "component": "dp-link",
            "release": "release-name",
        }

        # Ensure the core labels are in the pod template
        assert {
            "tier": "astronomer",
            "component": "dp-link",
            "release": "release-name",
            "app": "dp-link",
            "plane": "unified",
        }.items() <= dp_link_deployment["spec"]["template"]["metadata"]["labels"].items()

        c_by_name = get_containers_by_name(dp_link_deployment)
        assert len(c_by_name) == 1
        dp_link_container = c_by_name["dp-link"]

        assert dp_link_container["image"].startswith("quay.io/astronomer/ap-houston-api:")
        assert dp_link_container["securityContext"]["readOnlyRootFilesystem"]

        # Verify all environment variables are set with default values
        dp_link_env = get_env_vars_dict(dp_link_container["env"])

        assert dp_link_env["CLAIM_INTERVAL_SECONDS"] == "30"
        assert dp_link_env["LEASE_RENEWAL_INTERVAL_SECONDS"] == "15"
        assert dp_link_env["LEASE_DURATION_SECONDS"] == "60"
        assert dp_link_env["UNREACHABLE_THRESHOLD_SECONDS"] == "90"
        assert dp_link_env["DEGRADED_THRESHOLD_SECONDS"] == "30"
        assert dp_link_env["RECONNECT_MAX_ATTEMPTS"] == "10"
        assert dp_link_env["INITIAL_RECONNECT_DELAY_SECONDS"] == "1"
        assert dp_link_env["MAX_RECONNECT_DELAY_SECONDS"] == "30"
        assert dp_link_env["RECONNECT_DELAY_MULTIPLIER"] == "2"
        assert dp_link_env["JITTER_FRACTION"] == "0.2"

    @pytest.mark.parametrize("plane_mode,docs_len", [("control", 1), ("data", 0), ("unified", 1)])
    def test_dp_link_deployment_control_mode(self, kube_version, plane_mode, docs_len):
        """Test that dp-link is deployed in control and unified modes, but not in data mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": plane_mode}}},
            show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
        )

        assert len(docs) == docs_len
        if docs_len != 0:
            assert docs[0]["spec"]["template"]["metadata"]["labels"]["plane"] == plane_mode

    def test_dp_link_deployment_disabled(self, kube_version):
        """Test that dp-link is not deployed when disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"dpLink": {"enabled": False}}},
            show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
        )

        assert len(docs) == 0

    def test_dp_link_deployment_custom_values(self, kube_version):
        """Test dp-link deployment with custom configuration values."""
        custom_values = {
            "astronomer": {
                "dpLink": {
                    "claimIntervalSeconds": 60,
                    "leaseRenewalIntervalSeconds": 30,
                    "leaseDurationSeconds": 120,
                    "unreachableThresholdSeconds": 180,
                    "degradedThresholdSeconds": 60,
                    "reconnectMaxAttempts": 20,
                    "initialReconnectDelaySeconds": 2,
                    "maxReconnectDelaySeconds": 60,
                    "reconnectDelayMultiplier": 3,
                    "jitterFraction": 0.5,
                    "replicas": 5,
                }
            }
        }
        docs = render_chart(
            kube_version=kube_version,
            values=custom_values,
            show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
        )

        assert len(docs) == 1
        assert docs[0]["spec"]["replicas"] == 5
        c_by_name = get_containers_by_name(docs[0])
        dp_link_env = get_env_vars_dict(c_by_name["dp-link"]["env"])

        assert dp_link_env["CLAIM_INTERVAL_SECONDS"] == "60"
        assert dp_link_env["LEASE_RENEWAL_INTERVAL_SECONDS"] == "30"
        assert dp_link_env["LEASE_DURATION_SECONDS"] == "120"
        assert dp_link_env["UNREACHABLE_THRESHOLD_SECONDS"] == "180"
        assert dp_link_env["DEGRADED_THRESHOLD_SECONDS"] == "60"
        assert dp_link_env["RECONNECT_MAX_ATTEMPTS"] == "20"
        assert dp_link_env["INITIAL_RECONNECT_DELAY_SECONDS"] == "2"
        assert dp_link_env["MAX_RECONNECT_DELAY_SECONDS"] == "60"
        assert dp_link_env["RECONNECT_DELAY_MULTIPLIER"] == "3"
        assert dp_link_env["JITTER_FRACTION"] == "0.5"

    def test_dp_link_deployment_with_pod_annotations(self, kube_version):
        """Test dp-link deployment with custom pod annotations."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"dpLink": {"podAnnotations": {"custom-key": "custom-value"}}}},
            show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
        )

        assert len(docs) == 1
        annotations = docs[0]["spec"]["template"]["metadata"]["annotations"]
        assert "custom-key" in annotations
        assert annotations["custom-key"] == "custom-value"

    def test_dp_link_deployment_private_registry(self, kube_version):
        """Test dp-link deployment with private registry."""
        secret_name = "my-registry-secret"
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"privateRegistry": {"enabled": True, "secretName": secret_name}}},
            show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
        )

        assert len(docs) == 1
        image_pull_secrets = docs[0]["spec"]["template"]["spec"].get("imagePullSecrets", [])
        assert any(secret["name"] == secret_name for secret in image_pull_secrets)
