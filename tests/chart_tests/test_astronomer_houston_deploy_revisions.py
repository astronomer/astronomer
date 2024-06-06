from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerHoustonDeployRevisionsCronjobs:
    def test_astronomer_cleanup_deploy_revisons_cron_defaults(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {"cleanupDeployRevisions": {"enabled": False}}
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-deploy-revisions-cronjob.yaml",
            ],
        )
        assert len(docs) == 0

    def test_astronomer_cleanup_deploy_revisons_cron_feature_enabled(
        self, kube_version
    ):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {"houston": {"cleanupDeployRevisions": {"enabled": True}}}
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-deploy-revisions-cronjob.yaml",
            ],
        )

        assert len(docs) == 1
        assert docs[0]["kind"] == "CronJob"
        assert (
            docs[0]["metadata"]["name"]
            == "release-name-houston-cleanup-deploy-revisions"
        )
        assert docs[0]["spec"]["schedule"] == "11 23 * * *"
        assert docs[0]["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][
            0
        ]["securityContext"] == {"runAsNonRoot": True}

    def test_astronomer_cleanup_deploy_revisons_cron_custom_schedule(
        self, kube_version
    ):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "cleanupDeployRevisions": {
                            "enabled": True,
                            "schedule": "1 2 3 4 5",
                        }
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-deploy-revisions-cronjob.yaml",
            ],
        )

        assert len(docs) == 1
        assert docs[0]["kind"] == "CronJob"
        assert (
            docs[0]["metadata"]["name"]
            == "release-name-houston-cleanup-deploy-revisions"
        )
        assert docs[0]["spec"]["schedule"] == "1 2 3 4 5"
