import pytest
from tests import supported_k8s_versions
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
            show_only=["charts/astronomer/templates/houston/helm-hooks/houston-au-strategy-job.yaml"],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "Job"
        assert docs[0]["metadata"]["name"] == "release-name-update-resource-strategy"

        assert docs[0]["spec"]["template"]["spec"]["containers"][0]["args"] == ["update-deployments-resource-mode"]
