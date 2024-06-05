from tests.chart_tests.helm_template_generator import render_chart
import pytest
import yaml
from tests import get_cronjob_containerspec_by_name, supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerHoustonAirflowDbCleanupCronjob:
    def test_astronomer_airflow_db_cleanup_cron_defaults(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "cleanupAirflowDb": {"enabled": False},
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-airflow-db-cronjob.yaml",
            ],
        )
        assert len(docs) == 0

    def test_astronomer_airflow_db_cleanup_cron_feature_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "cleanupAirflowDb": {"enabled": True, "schedule": "23 5 * * *"}
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-airflow-db-cronjob.yaml",
            ],
        )

        assert len(docs) == 1
        job_container_by_name = get_cronjob_containerspec_by_name(docs[0])
        assert docs[0]["kind"] == "CronJob"
        assert (
            docs[0]["metadata"]["name"]
            == "release-name-houston-cleanup-airflow-db-data"
        )
        assert docs[0]["spec"]["schedule"] == "23 5 * * *"
        assert job_container_by_name["cleanup"]["securityContext"] == {
            "runAsNonRoot": True
        }

    def test_astronomer_airflow_db_cleanup_cron_custom_schedule(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "securityContext": {"allowPriviledgeEscalation": False},
                    "houston": {
                        "cleanupAirflowDb": {"enabled": True, "schedule": "22 5 * * *"}
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-airflow-db-cronjob.yaml",
            ],
        )

        assert len(docs) == 1
        job_container_by_name = get_cronjob_containerspec_by_name(docs[0])
        assert docs[0]["kind"] == "CronJob"
        assert (
            docs[0]["metadata"]["name"]
            == "release-name-houston-cleanup-airflow-db-data"
        )
        assert docs[0]["spec"]["schedule"] == "22 5 * * *"
        assert job_container_by_name["cleanup"]["securityContext"] == {
            "runAsNonRoot": True,
            "allowPriviledgeEscalation": False,
        }

    def test_houston_configmap_with_cleanup_enabled(self, kube_version):
        """Validate the houston configmap and its embedded data with
        cleanupAirflowDb."""

        docs = render_chart(
            values={"astronomer": {"houston": {"cleanupAirflowDb": {"enabled": True}}}},
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        doc = docs[0]
        prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod_yaml["deployments"]["cleanupAirflowDb"]["enabled"] is True
