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
        assert dp_link_container["command"] == ["/houston/bin/entrypoint"]
        assert dp_link_container["args"] == ["yarn", "run", "dplink"]

        # Verify all environment variables are set with default values
        dp_link_env = get_env_vars_dict(dp_link_container["env"])
        assert dp_link_env["NAMESPACE"] == "default"
        assert dp_link_env["JWT__CERT_PATH"] == "/etc/houston/tls/self"

        # Check that houston environment variables are present (e.g., database, JWT config)
        # These come from houston_environment helper
        assert "DATABASE__CONNECTION" in dp_link_env or "DATABASE_URL" in dp_link_env
        assert dp_link_env["DB_NAME"] == "release-name-houston"

        # Verify DP-Link specific environment variables are set with default values
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

        volumes = {v["name"]: v for v in docs[0]["spec"]["template"]["spec"]["volumes"]}
        # Check required volumes
        assert "etc-ssl-certs" in volumes
        assert volumes["etc-ssl-certs"]["emptyDir"] == {}
        assert "tmp" in volumes
        assert volumes["tmp"]["emptyDir"] == {}

    def test_dp_link_deployment_with_custom_probes(self, kube_version):
        """Test dp-link deployment with custom liveness and readiness probes."""
        custom_probes = {
            "livenessProbe": {
                "httpGet": {"path": "/health", "port": 8080},
                "initialDelaySeconds": 30,
                "periodSeconds": 10,
            },
            "readinessProbe": {
                "httpGet": {"path": "/ready", "port": 8080},
                "initialDelaySeconds": 10,
                "periodSeconds": 5,
            },
        }
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"dpLink": custom_probes}},
            show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        dp_link_container = c_by_name["dp-link"]

        assert "livenessProbe" in dp_link_container
        assert dp_link_container["livenessProbe"]["httpGet"]["path"] == "/health"
        assert dp_link_container["livenessProbe"]["initialDelaySeconds"] == 30

        assert "readinessProbe" in dp_link_container
        assert dp_link_container["readinessProbe"]["httpGet"]["path"] == "/ready"
        assert dp_link_container["readinessProbe"]["initialDelaySeconds"] == 10

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
                    "prismaConnectionLimit": "50",
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
        assert dp_link_env["PRISMA_CONNECTION_LIMIT"] == "50"

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

    def test_dp_link_deployment_init_container_copy_certs(self, kube_version):
        """Test that the init container properly copies SSL certificates."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
        )

        assert len(docs) == 1
        init_containers = docs[0]["spec"]["template"]["spec"]["initContainers"]
        assert len(init_containers) == 1

        init_container = init_containers[0]
        assert init_container["name"] == "etc-ssl-certs-copier"
        assert "cp -r /etc/ssl/certs" in init_container["command"][2]

        # Verify volume mount
        volume_mounts = {vm["name"]: vm["mountPath"] for vm in init_container["volumeMounts"]}
        assert volume_mounts["etc-ssl-certs"] == "/etc/ssl/certs_copy"

    def test_dp_link_user_provided_env_vars_and_secret_vars(self, kube_version):
        """Test that user-provided env vars and secret vars are injected into the dp-link container."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "dpLink": {
                        "env": [
                            {"name": "MY_CUSTOM_VAR", "value": "custom-value"},
                            {"name": "ANOTHER_VAR", "value": "another-value"},
                        ],
                        "secret": [
                            {"envName": "MY_SECRET_VAR", "secretName": "my-secret", "secretKey": "my-key"},
                            {"envName": "ANOTHER_SECRET", "secretName": "other-secret"},
                        ],
                    }
                }
            },
            show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["dp-link"]["env"])
        assert env_vars["MY_CUSTOM_VAR"] == "custom-value"
        assert env_vars["ANOTHER_VAR"] == "another-value"
        assert env_vars["MY_SECRET_VAR"] == {"secretKeyRef": {"name": "my-secret", "key": "my-key"}}
        assert env_vars["ANOTHER_SECRET"] == {"secretKeyRef": {"name": "other-secret", "key": "value"}}
