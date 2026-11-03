import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart

# Every bootstrapper container writes the same Houston connection secret, so they
# must all pass the same limit, or the last one to start would decide it.
#
# houston-cp-refresh-job is covered separately: it renders only in HA mode.
BOOTSTRAPPER_TEMPLATES = [
    "charts/astronomer/templates/houston/api/houston-deployment.yaml",
    "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
    "charts/astronomer/templates/houston/helm-hooks/houston-db-migration-job.yaml",
    "charts/astronomer/templates/houston/helm-hooks/houston-upgrade-deployments-job.yaml",
]
CP_REFRESH_JOB = "charts/astronomer/templates/houston/helm-hooks/houston-cp-refresh-job.yaml"
DP_LINK_DEPLOYMENT = "charts/astronomer/templates/dp-link/dp-link-deployment.yaml"
HA_VALUES = {
    "global": {
        "plane": {"mode": "control"},
        "controlPlaneHA": {"enabled": True, "globalBaseDomain": "astro.example.com"},
    }
}


def _bootstrapper_limit(kube_version, template, values=None):
    docs = render_chart(kube_version=kube_version, values=values or {}, show_only=[template])
    assert len(docs) == 1
    containers = get_containers_by_name(docs[0], include_init_containers=True)
    return get_env_vars_dict(containers["houston-bootstrapper"]["env"]).get("PRISMA_CONNECTION_LIMIT")


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestHoustonConnectionLimit:
    @pytest.mark.parametrize("template", BOOTSTRAPPER_TEMPLATES)
    def test_every_bootstrapper_passes_the_default_limit(self, kube_version, template):
        assert _bootstrapper_limit(kube_version, template) == "20"

    @pytest.mark.parametrize("template", BOOTSTRAPPER_TEMPLATES)
    def test_every_bootstrapper_passes_a_custom_limit(self, kube_version, template):
        values = {"astronomer": {"houston": {"prismaConnectionLimit": 35}}}
        assert _bootstrapper_limit(kube_version, template, values) == "35"

    def test_the_ha_only_cp_refresh_job_passes_the_limit(self, kube_version):
        assert _bootstrapper_limit(kube_version, CP_REFRESH_JOB, HA_VALUES) == "20"

    def test_dp_link_uses_the_limit_in_houstons_connection_secret(self, kube_version):
        """dp-link has no limit of its own: it reads Houston's connection secret, limit included."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=[DP_LINK_DEPLOYMENT],
        )
        assert len(docs) == 1
        env = get_containers_by_name(docs[0])["dp-link"]["env"]
        connection = next(e for e in env if e["name"] == "DATABASE__CONNECTION")
        assert connection["valueFrom"]["secretKeyRef"] == {"name": "release-name-houston-backend", "key": "connection"}
        assert "PRISMA_CONNECTION_LIMIT" not in {e["name"] for e in env}
