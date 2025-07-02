import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerHoustonClusterAuditsCronJobs:
    def test_astronomer_cleanup_cluster_audits_cron_defaults(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"cleanupClusterAudits": {"enabled": False}}}},
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-cluster-audits-cronjob.yaml",
            ],
        )
        assert len(docs) == 0

    def test_astronomer_cleanup_cluster_audits_cron_feature_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"cleanupClusterAudits": {"enabled": True}}}},
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-cluster-audits-cronjob.yaml",
            ],
        )

        assert len(docs) == 1
        assert docs[0]["kind"] == "CronJob"
        assert docs[0]["metadata"]["name"] == "release-name-houston-cleanup-cluster-audits"
        assert docs[0]["metadata"]["labels"]["component"] == "houston-cleanup"
        spec = docs[0]["spec"]["jobTemplate"]["spec"]["template"]
        assert spec["metadata"]["labels"]["component"] == "houston-cleanup"
        assert docs[0]["spec"]["schedule"] == "49 23 * * *"
        assert spec["spec"]["containers"][0]["securityContext"] == {"runAsNonRoot": True}

    def test_astronomer_cleanup_cluster_audits_cron_custom_schedule(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "cleanupClusterAudits": {
                            "enabled": True,
                            "schedule": "1 2 3 4 5",
                        }
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-cluster-audits-cronjob.yaml",
            ],
        )

        assert len(docs) == 1
        assert docs[0]["kind"] == "CronJob"
        assert docs[0]["metadata"]["name"] == "release-name-houston-cleanup-cluster-audits"
        assert docs[0]["spec"]["schedule"] == "1 2 3 4 5"
