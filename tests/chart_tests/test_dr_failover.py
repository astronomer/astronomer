import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


def failover_values(plane_mode):
    """Return values with dataPlaneFailover enabled for the given plane mode."""
    return {
        "global": {
            "plane": {"mode": plane_mode},
            "features": {"dataPlaneFailover": {"enabled": True}},
        },
    }


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestDataPlaneFailoverFlag:
    """Tests for the global.features.dataPlaneFailover.enabled feature flag."""

    # --- Data-plane components (mode=data) ---

    def test_flag_data_mode_enables_pilot(self, kube_version):
        """Flag in data mode renders pilot deployment without pilot.enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values=failover_values("data"),
            show_only=["charts/astronomer/templates/pilot/pilot-deployment.yaml"],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "Deployment"
        assert docs[0]["metadata"]["name"] == "release-name-pilot"

    def test_flag_data_mode_enables_pilot_serviceaccount(self, kube_version):
        """Flag in data mode renders pilot service account."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                    "rbacEnabled": True,
                    "features": {"dataPlaneFailover": {"enabled": True}},
                },
            },
            show_only=["charts/astronomer/templates/pilot/pilot-serviceaccount.yaml"],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "ServiceAccount"

    def test_flag_data_mode_enables_flightdeck(self, kube_version):
        """Flag in data mode renders flightDeck init containers and DSN env var on commander."""
        docs = render_chart(
            kube_version=kube_version,
            values=failover_values("data"),
            show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
        )
        assert len(docs) == 1
        init_containers = docs[0]["spec"]["template"]["spec"]["initContainers"]
        init_names = [c["name"] for c in init_containers]
        assert "flightdeck-bootstrapper" in init_names
        assert "flightdeck-db-migrations" in init_names

        containers = docs[0]["spec"]["template"]["spec"]["containers"]
        env_vars = get_env_vars_dict(containers[0]["env"])
        assert "COMMANDER_FLIGHTDECK_DSN" in env_vars

    def test_flag_data_mode_sets_commander_failover_env(self, kube_version):
        """Flag in data mode sets COMMANDER_DATAPLANE_FAILOVER_ENABLED=true on commander."""
        docs = render_chart(
            kube_version=kube_version,
            values=failover_values("data"),
            show_only=["charts/astronomer/templates/commander/commander-deployment.yaml"],
        )
        assert len(docs) == 1
        containers = docs[0]["spec"]["template"]["spec"]["containers"]
        env_vars = get_env_vars_dict(containers[0]["env"])
        assert env_vars["COMMANDER_DATAPLANE_FAILOVER_ENABLED"] == "true"

    def test_flag_data_mode_sets_flightdeck_configmap(self, kube_version):
        """Flag in data mode renders flightdeck_db_name in cluster-local-data configmap."""
        docs = render_chart(
            kube_version=kube_version,
            values=failover_values("data"),
            show_only=["charts/astronomer/templates/cluster-local-data.yaml"],
        )
        assert len(docs) == 1
        assert "flightdeck_db_name" in docs[0]["data"]

    def test_flag_data_mode_enables_pilot_flightdeck_dsn(self, kube_version):
        """Flag in data mode injects COMMANDER_FLIGHTDECK_DSN into pilot."""
        docs = render_chart(
            kube_version=kube_version,
            values=failover_values("data"),
            show_only=["charts/astronomer/templates/pilot/pilot-deployment.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["pilot"]["env"])
        assert "COMMANDER_FLIGHTDECK_DSN" in env_vars

    # --- Control-plane components (mode=control) ---

    def test_flag_control_mode_enables_navigator(self, kube_version):
        """Flag in control mode renders navigator deployment without navigator.enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values=failover_values("control"),
            show_only=["charts/astronomer/templates/navigator/navigator-deployment.yaml"],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "Deployment"
        assert docs[0]["metadata"]["name"] == "release-name-navigator"

    def test_flag_control_mode_enables_navigator_serviceaccount(self, kube_version):
        """Flag in control mode renders navigator service account."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "control"},
                    "rbacEnabled": True,
                    "features": {"dataPlaneFailover": {"enabled": True}},
                },
            },
            show_only=["charts/astronomer/templates/navigator/navigator-serviceaccount.yaml"],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "ServiceAccount"

    def test_flag_control_mode_enables_dp_link(self, kube_version):
        """Flag in control mode renders dp-link deployment without dpLink.enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "control"},
                    "features": {"dataPlaneFailover": {"enabled": True}},
                },
                "astronomer": {"dpLink": {"enabled": False}},
            },
            show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "Deployment"

    def test_flag_control_mode_enables_dispatcher(self, kube_version):
        """Flag in control mode sets DISPATCHER_ENABLED=true on houston-worker."""
        docs = render_chart(
            kube_version=kube_version,
            values=failover_values("control"),
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0], include_init_containers=False)
        env_vars = get_env_vars_dict(c_by_name["houston"]["env"])
        assert env_vars["DISPATCHER_ENABLED"] == "true"

    # --- Cross-mode isolation ---

    def test_flag_data_mode_does_not_enable_navigator(self, kube_version):
        """Flag in data mode does NOT render navigator."""
        docs = render_chart(
            kube_version=kube_version,
            values=failover_values("data"),
            show_only=["charts/astronomer/templates/navigator/navigator-deployment.yaml"],
        )
        assert len(docs) == 0

    def test_flag_data_mode_does_not_enable_dp_link(self, kube_version):
        """Flag in data mode does NOT render dp-link."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                    "features": {"dataPlaneFailover": {"enabled": True}},
                },
                "astronomer": {"dpLink": {"enabled": False}},
            },
            show_only=["charts/astronomer/templates/dp-link/dp-link-deployment.yaml"],
        )
        assert len(docs) == 0

    def test_flag_control_mode_does_not_enable_pilot(self, kube_version):
        """Flag in control mode does NOT render pilot."""
        docs = render_chart(
            kube_version=kube_version,
            values=failover_values("control"),
            show_only=["charts/astronomer/templates/pilot/pilot-deployment.yaml"],
        )
        assert len(docs) == 0

    # --- Unified mode: flag has no effect ---

    def test_flag_unified_mode_does_not_enable_pilot(self, kube_version):
        """Flag in unified mode does NOT auto-enable pilot."""
        docs = render_chart(
            kube_version=kube_version,
            values=failover_values("unified"),
            show_only=["charts/astronomer/templates/pilot/pilot-deployment.yaml"],
        )
        assert len(docs) == 0

    def test_flag_unified_mode_does_not_enable_navigator(self, kube_version):
        """Flag in unified mode does NOT auto-enable navigator."""
        docs = render_chart(
            kube_version=kube_version,
            values=failover_values("unified"),
            show_only=["charts/astronomer/templates/navigator/navigator-deployment.yaml"],
        )
        assert len(docs) == 0

    # --- Flag disabled: no effect ---

    def test_flag_disabled_no_pilot(self, kube_version):
        """With flag disabled, pilot is not rendered (pilot.enabled defaults to false)."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                    "features": {"dataPlaneFailover": {"enabled": False}},
                },
            },
            show_only=["charts/astronomer/templates/pilot/pilot-deployment.yaml"],
        )
        assert len(docs) == 0

    def test_flag_disabled_no_navigator(self, kube_version):
        """With flag disabled, navigator is not rendered (navigator.enabled defaults to false)."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "control"},
                    "features": {"dataPlaneFailover": {"enabled": False}},
                },
            },
            show_only=["charts/astronomer/templates/navigator/navigator-deployment.yaml"],
        )
        assert len(docs) == 0
