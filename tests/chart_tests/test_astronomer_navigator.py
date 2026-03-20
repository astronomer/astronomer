import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerNavigator:
    show_only = ["charts/astronomer/templates/navigator/navigator-deployment.yaml"]

    @pytest.mark.parametrize(
        "plane_mode,expected_count",
        [
            ("control", 1),
            ("unified", 1),
            ("data", 0),
        ],
    )
    def test_navigator_deployment_plane_mode(self, kube_version, plane_mode, expected_count):
        """Test that navigator deployment only renders in control or unified plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": plane_mode}},
                "astronomer": {"navigator": {"enabled": True}},
            },
            show_only=self.show_only,
        )
        assert len(docs) == expected_count
        if expected_count:
            assert docs[0]["kind"] == "Deployment"
            assert docs[0]["metadata"]["name"] == "release-name-navigator"

    def test_navigator_deployment_disabled(self, kube_version):
        """Test that navigator deployment is not rendered when disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"navigator": {"enabled": False}},
            },
            show_only=self.show_only,
        )
        assert len(docs) == 0

    def test_navigator_deployment_default_values(self, kube_version):
        """Test that navigator deployment renders correctly with default values."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"navigator": {"enabled": True}},
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "Deployment"
        assert doc["spec"]["replicas"] == 3

        c_by_name = get_containers_by_name(doc)
        assert "navigator" in c_by_name
        navigator = c_by_name["navigator"]

        # Uses houston image
        assert "ap-houston-api" in navigator["image"]

        # Command is 'yarn run navigator'
        assert navigator["command"] == ["yarn", "run", "navigator"]

    def test_navigator_deployment_env_vars_defaults(self, kube_version):
        """Test that navigator deployment exposes all expected env vars with correct defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"navigator": {"enabled": True}},
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["navigator"]["env"])

        # Component flag
        assert env_vars["NAVIGATOR_ENABLED"] == "false"

        # Failover request reconcile loop
        assert env_vars["FAILOVER_REQUEST_RECONCILER_INTERVAL_SECONDS"] == "10"

        # Deployment admission control loop
        assert env_vars["DEPLOYMENT_ADMIT_FOR_IN_PROGRESS_MISSIONS_INTERVAL_SECONDS"] == "10"
        assert env_vars["DEPLOYMENT_ADMIT_FOR_PENDING_CLEANUP_MISSIONS_INTERVAL_SECONDS"] == "30"
        assert env_vars["DEPLOYMENT_CLAIM_BATCH_SIZE"] == "50"
        assert env_vars["DEPLOYMENT_ADMIT_BATCH_SIZE"] == "5"

        # Mission reconciler loop
        assert env_vars["MISSION_CLAIM_MIN_BATCH_SIZE"] == "10"
        assert env_vars["MISSION_PLAN_BATCH_SIZE"] == "5"
        assert env_vars["MISSION_RECONCILE_BATCH_SIZE"] == "5"
        assert env_vars["CLAIM_INTERVAL_SECONDS"] == "10"
        assert env_vars["CLAIM_FRACTION"] == "0.5"

        # Cleanup knobs
        assert env_vars["CLEANUP_INTERVAL_SECONDS"] == "300"
        assert env_vars["MISSION_CLEANUP_TTL"] == "604800"
        assert env_vars["FLIGHT_CLEANUP_TTL"] == "604800"

    def test_navigator_deployment_custom_env_vars(self, kube_version):
        """Test that navigator deployment reflects custom value overrides in env vars."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "unified"}},
                "astronomer": {
                    "navigator": {
                        "enabled": True,
                        "navigatorEnabled": True,
                        "failoverRequestReconcilerIntervalSeconds": 30,
                        "deploymentAdmitForInProgressMissionsIntervalSeconds": 20,
                        "deploymentAdmitForPendingCleanupMissionsIntervalSeconds": 60,
                        "deploymentClaimBatchSize": 100,
                        "deploymentAdmitBatchSize": 10,
                        "missionClaimMinBatchSize": 20,
                        "missionPlanBatchSize": 10,
                        "missionReconcileBatchSize": 10,
                        "claimIntervalSeconds": 15,
                        "claimFraction": 0.75,
                        "cleanupIntervalSeconds": 600,
                        "missionCleanupTtl": 86400,
                        "flightCleanupTtl": 172800,
                    }
                },
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["navigator"]["env"])

        assert env_vars["NAVIGATOR_ENABLED"] == "true"
        assert env_vars["FAILOVER_REQUEST_RECONCILER_INTERVAL_SECONDS"] == "30"
        assert env_vars["DEPLOYMENT_ADMIT_FOR_IN_PROGRESS_MISSIONS_INTERVAL_SECONDS"] == "20"
        assert env_vars["DEPLOYMENT_ADMIT_FOR_PENDING_CLEANUP_MISSIONS_INTERVAL_SECONDS"] == "60"
        assert env_vars["DEPLOYMENT_CLAIM_BATCH_SIZE"] == "100"
        assert env_vars["DEPLOYMENT_ADMIT_BATCH_SIZE"] == "10"
        assert env_vars["MISSION_CLAIM_MIN_BATCH_SIZE"] == "20"
        assert env_vars["MISSION_PLAN_BATCH_SIZE"] == "10"
        assert env_vars["MISSION_RECONCILE_BATCH_SIZE"] == "10"
        assert env_vars["CLAIM_INTERVAL_SECONDS"] == "15"
        assert env_vars["CLAIM_FRACTION"] == "0.75"
        assert env_vars["CLEANUP_INTERVAL_SECONDS"] == "600"
        assert env_vars["MISSION_CLEANUP_TTL"] == "86400"
        assert env_vars["FLIGHT_CLEANUP_TTL"] == "172800"

    def test_navigator_deployment_probe_customization(self, kube_version):
        """Test that navigator containers support customizable liveness and readiness probes."""
        probe = {"exec": {"command": ["/bin/true"]}}
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {
                    "navigator": {
                        "enabled": True,
                        "livenessProbe": probe,
                        "readinessProbe": probe,
                    }
                },
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        navigator = c_by_name["navigator"]
        assert navigator["livenessProbe"] == probe
        assert navigator["readinessProbe"] == probe

    def test_navigator_deployment_replicas(self, kube_version):
        """Test that navigator deployment respects the replicas setting."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"navigator": {"enabled": True, "replicas": 5}},
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        assert docs[0]["spec"]["replicas"] == 5
