from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonCronJobUpdateRootAdminPassword:
    def test_cronjob_update_root_admin_password(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {}}},
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-update-root-admin-password.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "CronJob"
        assert doc["spec"]["suspend"] is True
