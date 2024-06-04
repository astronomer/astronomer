import pytest
from tests import get_containers_by_name, supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonHookJob:
    def test_au_strategy_job_defaults(self, kube_version):
        """Test AU Strategy Job defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/astronomer/templates/houston/helm-hooks/houston-au-strategy-job.yaml"
            ],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert docs[0]["kind"] == "Job"
        assert docs[0]["metadata"]["name"] == "release-name-update-resource-strategy"

        assert c_by_name["post-upgrade-update-resource-strategy"]["args"] == [
            "update-deployments-resource-mode"
        ]

        assert c_by_name["post-upgrade-update-resource-strategy"][
            "securityContext"
        ] == {"runAsNonRoot": True}
