from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions


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

        assert doc["kind"] == "CronJob"
        assert doc["spec"]["schedule"] == "43 0 * * *"
        assert doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0][
            "args"
        ] == [
            "yarn",
            "check-runtime-updates",
            "--url=https://updates.astronomer.io/astronomer-runtime",
        ]

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
