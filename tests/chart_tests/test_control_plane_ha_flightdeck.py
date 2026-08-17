"""Tests for the CP-HA → flightdeck-store coupling (PINF-1093).

CP-HA introduces the same multi-CP message reordering that commander's flightdeck
version-guard CAS defends against, so on a data plane the flightdeck store
(bootstrapper + migrations + COMMANDER_FLIGHTDECK_DSN) must be provisioned when
global.controlPlaneHA.enabled is true — independent of global.dataPlaneFailover.

The gate lives in the shared `flightdeck.enabled` helper and is exercised via:
  * commander-deployment.yaml — flightdeck init containers + commander DSN env
  * cluster-local-data.yaml    — flightdeck_db_name configmap field
  * commander-flightdeck-role.yaml / -rolebinding.yaml — RBAC

Mirrors the dataPlaneFailover coverage in test_dr_failover.py.
"""

import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart

COMMANDER_FILE = "charts/astronomer/templates/commander/commander-deployment.yaml"
CLUSTER_LOCAL_DATA_FILE = "charts/astronomer/templates/cluster-local-data.yaml"
FLIGHTDECK_ROLE_FILE = "charts/astronomer/templates/commander/commander-flightdeck-role.yaml"
FLIGHTDECK_ROLEBINDING_FILE = "charts/astronomer/templates/commander/commander-flightdeck-rolebinding.yaml"


def cpha_values(plane_mode, **global_overrides):
    """Return values with controlPlaneHA enabled for the given plane mode.

    globalBaseDomain is required whenever controlPlaneHA is enabled
    (validate-controlplane-ha.yaml), so it is always supplied.
    """
    return {
        "global": {
            "plane": {"mode": plane_mode},
            "controlPlaneHA": {"enabled": True, "globalBaseDomain": "astro.example.com"},
            **global_overrides,
        },
    }


def _init_container_names(doc):
    return [c["name"] for c in doc["spec"]["template"]["spec"]["initContainers"]]


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestControlPlaneHAFlightdeck:
    """Tests for CP-HA provisioning the flightdeck store on data planes (PINF-1093)."""

    def test_data_mode_enables_flightdeck_on_commander(self, kube_version):
        """CP-HA in data mode renders flightdeck init containers and the commander DSN env."""
        docs = render_chart(
            kube_version=kube_version,
            values=cpha_values("data"),
            show_only=[COMMANDER_FILE],
        )
        assert len(docs) == 1
        init_names = _init_container_names(docs[0])
        assert "flightdeck-bootstrapper" in init_names
        assert "flightdeck-db-migrations" in init_names

        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["commander"]["env"])
        assert "COMMANDER_FLIGHTDECK_DSN" in env_vars

    def test_data_mode_sets_commander_cpha_env(self, kube_version):
        """CP-HA in data mode sets COMMANDER_CONTROL_PLANE_HA_ENABLED=true so commander initializes the store."""
        docs = render_chart(
            kube_version=kube_version,
            values=cpha_values("data"),
            show_only=[COMMANDER_FILE],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["commander"]["env"])
        assert env_vars["COMMANDER_CONTROL_PLANE_HA_ENABLED"] == "true"

    def test_cpha_disabled_commander_env_false(self, kube_version):
        """Without CP-HA, COMMANDER_CONTROL_PLANE_HA_ENABLED is false on commander."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=[COMMANDER_FILE],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["commander"]["env"])
        assert env_vars["COMMANDER_CONTROL_PLANE_HA_ENABLED"] == "false"

    def test_data_mode_sets_flightdeck_configmap(self, kube_version):
        """CP-HA in data mode renders flightdeck_db_name in cluster-local-data configmap."""
        docs = render_chart(
            kube_version=kube_version,
            values=cpha_values("data"),
            show_only=[CLUSTER_LOCAL_DATA_FILE],
        )
        assert len(docs) == 1
        assert "flightdeck_db_name" in docs[0]["data"]

    def test_data_mode_enables_flightdeck_rbac(self, kube_version):
        """CP-HA in data mode renders the flightdeck Role and RoleBinding (namespaced RBAC)."""
        docs = render_chart(
            kube_version=kube_version,
            values=cpha_values("data", rbac={"enabled": True}, clusterRoles=False),
            show_only=[FLIGHTDECK_ROLE_FILE, FLIGHTDECK_ROLEBINDING_FILE],
        )
        kinds = {d["kind"] for d in docs}
        assert kinds == {"Role", "RoleBinding"}

    def test_unified_mode_does_not_enable_flightdeck(self, kube_version):
        """CP-HA branch is gated on plane.mode == data: unified mode does NOT provision the store."""
        docs = render_chart(
            kube_version=kube_version,
            values=cpha_values("unified"),
            show_only=[COMMANDER_FILE],
        )
        assert len(docs) == 1
        init_names = _init_container_names(docs[0])
        assert "flightdeck-bootstrapper" not in init_names
        assert "flightdeck-db-migrations" not in init_names

        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["commander"]["env"])
        assert "COMMANDER_FLIGHTDECK_DSN" not in env_vars

    def test_disabled_no_flightdeck(self, kube_version):
        """Data plane with CP-HA and failover both off: flightdeck store is absent (no accidental always-on)."""
        values = {
            "global": {
                "plane": {"mode": "data"},
                "controlPlaneHA": {"enabled": False},
                "dataPlaneFailover": {"enabled": False},
            },
        }
        commander_docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[COMMANDER_FILE],
        )
        assert len(commander_docs) == 1
        init_names = _init_container_names(commander_docs[0])
        assert "flightdeck-bootstrapper" not in init_names
        assert "flightdeck-db-migrations" not in init_names
        c_by_name = get_containers_by_name(commander_docs[0])
        assert "COMMANDER_FLIGHTDECK_DSN" not in get_env_vars_dict(c_by_name["commander"]["env"])

        cm_docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[CLUSTER_LOCAL_DATA_FILE],
        )
        assert len(cm_docs) == 1
        assert "flightdeck_db_name" not in cm_docs[0]["data"]
