from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import get_cronjob_containerspec_by_name, supported_k8s_versions


default_houston_resource_spec = {"limits": {"cpu": "1000m", "memory": "2048Mi"}, "requests": {"cpu": "500m", "memory": "1024Mi"}}


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonCronJobAirflowUpdates:
    def test_cronjob_airflow_updates_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"updateAirflowCheck": {"enabled": True}}}},
            show_only=["charts/astronomer/templates/houston/cronjobs/houston-check-airflow-version-updates-cronjob.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        job_container_by_name = get_cronjob_containerspec_by_name(docs[0])

        assert doc["kind"] == "CronJob"
        assert doc["spec"]["schedule"] == "57 * * * *"
        assert job_container_by_name["update-check"]["args"] == [
            "yarn",
            "check-airflow-updates",
            "--url=https://updates.astronomer.io/astronomer-certified",
        ]
        assert job_container_by_name["update-check"]["securityContext"] == {"runAsNonRoot": True}
        assert default_houston_resource_spec == job_container_by_name["update-check"]["resources"]

    def test_cronjob_airflow_updates_enabled_with_securityContext_overrides(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "securityContext": {"allowPriviledgeEscalation": False},
                    "houston": {"updateAirflowCheck": {"enabled": True}},
                }
            },
            show_only=["charts/astronomer/templates/houston/cronjobs/houston-check-airflow-version-updates-cronjob.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        job_container_by_name = get_cronjob_containerspec_by_name(docs[0])

        assert doc["kind"] == "CronJob"
        assert doc["spec"]["schedule"] == "57 * * * *"
        assert job_container_by_name["update-check"]["args"] == [
            "yarn",
            "check-airflow-updates",
            "--url=https://updates.astronomer.io/astronomer-certified",
        ]
        assert job_container_by_name["update-check"]["securityContext"] == {
            "runAsNonRoot": True,
            "allowPriviledgeEscalation": False,
        }

    def test_cronjob_airflow_updates_disabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"updateAirflowCheck": {"enabled": False}}}},
            show_only=["charts/astronomer/templates/houston/cronjobs/houston-check-airflow-version-updates-cronjob.yaml"],
        )

        assert len(docs) == 0
