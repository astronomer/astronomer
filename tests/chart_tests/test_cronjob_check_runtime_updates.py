from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import get_cronjob_containerspec_by_name, supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonCronJobAstroRuntimeUpdates:
    def test_cronjob_runtime_updates_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {"houston": {"updateRuntimeCheck": {"enabled": True}}}
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-check-runtime-updates.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        job_container_by_name = get_cronjob_containerspec_by_name(docs[0])

        assert doc["kind"] == "CronJob"
        assert doc["spec"]["schedule"] == "43 0 * * *"
        assert job_container_by_name["update-check"]["args"] == [
            "yarn",
            "check-runtime-updates",
            "--url=https://updates.astronomer.io/astronomer-runtime",
        ]
        assert job_container_by_name["update-check"]["securityContext"] == {
            "runAsNonRoot": True
        }

    def test_cronjob_runtime_updates_enabled_with_securityContext_overrides(
        self, kube_version
    ):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "securityContext": {"allowPriviledgeEscalation": False},
                    "houston": {"updateRuntimeCheck": {"enabled": True}},
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-check-runtime-updates.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        job_container_by_name = get_cronjob_containerspec_by_name(docs[0])

        assert doc["kind"] == "CronJob"
        assert doc["spec"]["schedule"] == "43 0 * * *"
        assert job_container_by_name["update-check"]["args"] == [
            "yarn",
            "check-runtime-updates",
            "--url=https://updates.astronomer.io/astronomer-runtime",
        ]
        assert job_container_by_name["update-check"]["securityContext"] == {
            "runAsNonRoot": True,
            "allowPriviledgeEscalation": False,
        }

    def test_cronjob_runtime_updates_disabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {"houston": {"updateRuntimeCheck": {"enabled": False}}}
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-check-runtime-updates.yaml"
            ],
        )

        assert len(docs) == 0
