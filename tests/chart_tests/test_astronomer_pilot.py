import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerPilot:
    show_only = ["charts/astronomer/templates/pilot/pilot-deployment.yaml"]

    @pytest.mark.parametrize(
        "plane_mode,expected_count",
        [
            ("data", 1),
            ("control", 0),
            ("unified", 0),
        ],
    )
    def test_pilot_deployment_plane_mode(self, kube_version, plane_mode, expected_count):
        """Test that pilot deployment is only rendered in data plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": plane_mode}}},
            show_only=self.show_only,
        )
        assert len(docs) == expected_count
        if expected_count:
            assert docs[0]["kind"] == "Deployment"
            assert docs[0]["metadata"]["name"] == "release-name-pilot"

    def test_pilot_deployment_default_values(self, kube_version):
        """Test that pilot deployment renders correctly with default values."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=self.show_only,
        )
        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "Deployment"
        assert doc["spec"]["replicas"] == 3

        c_by_name = get_containers_by_name(doc)
        assert "pilot" in c_by_name
        pilot = c_by_name["pilot"]

        # Uses commander image
        assert "ap-commander" in pilot["image"]

        # Command is 'commander pilot'
        assert pilot["command"] == ["commander", "pilot"]

    def test_pilot_deployment_env_vars_defaults(self, kube_version):
        """Test that pilot deployment exposes all expected env vars with defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=self.show_only,
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["pilot"]["env"])

        # Infrastructure
        assert "release-name-commander-headless" in env_vars["PILOT_COMMANDER_ADDR"]
        assert "50051" in env_vars["PILOT_COMMANDER_ADDR"]
        assert "COMMANDER_FLIGHTDECK_DSN" not in env_vars

        # Claim knobs
        assert env_vars["PILOT_MAX_INFLIGHT_PER_WORKER"] == "5"
        assert env_vars["PILOT_CLAIM_POLL_INTERVAL_MS"] == "5000"
        assert env_vars["PILOT_MAX_BATCH_CLAIM_SIZE"] == "10"

        # Leasing knobs
        assert env_vars["PILOT_LEASE_TTL_SECONDS"] == "60"
        assert env_vars["PILOT_LEASE_RENEW_TICK_SECONDS"] == "5"
        assert env_vars["PILOT_LEASE_RENEW_THRESHOLD_SECONDS"] == "20"

        # Retry knobs
        assert env_vars["PILOT_MAX_ATTEMPTS_PER_LEASE"] == "3"
        assert env_vars["PILOT_MAX_ATTEMPTS_PER_FLIGHT"] == "25"
        assert env_vars["PILOT_RETRY_BASE_INTERVAL_MS"] == "250"
        assert env_vars["PILOT_RETRY_MAX_INTERVAL_MS"] == "5000"
        assert env_vars["PILOT_RETRY_COOLOFF_SECONDS"] == "30"
        assert env_vars["PILOT_RETRY_MULTIPLIER"] == "2"
        assert env_vars["PILOT_RETRY_JITTER_PCT"] == "0.2"

        # Circuit breaker knobs
        assert env_vars["PILOT_CB_FAILURE_THRESHOLD"] == "10"
        assert env_vars["PILOT_CB_COOLOFF_SECONDS"] == "30"
        assert env_vars["PILOT_CB_PROBE_MAX_INFLIGHT"] == "1"

    def test_pilot_flightdeck_dsn_injected_when_enabled(self, kube_version):
        """Test that COMMANDER_FLIGHTDECK_DSN is injected from secret when flightDeck is enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                    "flightDeck": {"enabled": True},
                }
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["pilot"]["env"])

        assert env_vars["COMMANDER_FLIGHTDECK_DSN"] == {
            "secretKeyRef": {
                "name": "release-name-flightdeck-backend",
                "key": "connection",
            }
        }

    def test_pilot_uses_commander_image(self, kube_version):
        """Test that pilot uses the same image as commander."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "astronomer": {"images": {"commander": {"tag": "test-tag-123"}}},
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert "test-tag-123" in c_by_name["pilot"]["image"]

    def test_pilot_custom_replicas(self, kube_version):
        """Test that pilot replica count can be overridden."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "astronomer": {"pilot": {"replicas": 5}},
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        assert docs[0]["spec"]["replicas"] == 5

    def test_pilot_custom_env_vars(self, kube_version):
        """Test that pilot knob values can be overridden via values."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "astronomer": {
                    "pilot": {
                        "maxInflightPerWorker": 10,
                        "claimPollIntervalMs": 1000,
                        "leaseTtlSeconds": 120,
                        "cbFailureThreshold": 5,
                    }
                },
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["pilot"]["env"])

        assert env_vars["PILOT_MAX_INFLIGHT_PER_WORKER"] == "10"
        assert env_vars["PILOT_CLAIM_POLL_INTERVAL_MS"] == "1000"
        assert env_vars["PILOT_LEASE_TTL_SECONDS"] == "120"
        assert env_vars["PILOT_CB_FAILURE_THRESHOLD"] == "5"

    def test_pilot_probe_customization(self, kube_version):
        """Test that liveness and readiness probes can be customized."""
        probe = {"exec": {"command": ["/bin/true"]}}
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "astronomer": {
                    "pilot": {
                        "livenessProbe": probe,
                        "readinessProbe": probe,
                    }
                },
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        pilot = c_by_name["pilot"]
        assert pilot["livenessProbe"] == probe
        assert pilot["readinessProbe"] == probe

    def test_pilot_serviceaccount_created_with_rbac(self, kube_version):
        """Test that pilot service account is created when rbac is enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                    "rbacEnabled": True,
                }
            },
            show_only=["charts/astronomer/templates/pilot/pilot-serviceaccount.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ServiceAccount"
        assert doc["metadata"]["name"] == "release-name-pilot"

    def test_pilot_serviceaccount_not_created_without_rbac(self, kube_version):
        """Test that pilot service account is not created when rbac is disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                    "rbacEnabled": False,
                }
            },
            show_only=["charts/astronomer/templates/pilot/pilot-serviceaccount.yaml"],
        )
        assert len(docs) == 0

    def test_pilot_commander_addr_format(self, kube_version):
        """Test that PILOT_COMMANDER_ADDR is set to the commander headless service address."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=self.show_only,
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["pilot"]["env"])

        expected_addr = "release-name-commander-headless.default.svc.cluster.local.:50051"
        assert env_vars["PILOT_COMMANDER_ADDR"] == expected_addr
