from tests.chart_tests.helm_template_generator import render_chart
import pytest
import yaml
from tests import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerHoustonTaskMetricsCronjobs:
    def test_astronomer_cleanup_task_usage_cron_defaults(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"taskUsageMetricsEnabled": False}},
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-task-data-cronjob.yaml",
            ],
        )
        assert len(docs) == 0

    def test_astronomer_cleanup_task_usage_cron_feature_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"taskUsageMetricsEnabled": True}},
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-task-data-cronjob.yaml",
            ],
        )

        assert len(docs) == 1
        assert docs[0]["kind"] == "CronJob"
        assert (
            docs[0]["metadata"]["name"]
            == "release-name-houston-cleanup-task-usage-data"
        )
        assert docs[0]["spec"]["schedule"] == "40 23 * * *"

    def test_astronomer_populate_daily_task_metrics_defaults(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"taskUsageMetricsEnabled": False}},
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-populate-daily-task-metrics.yaml",
            ],
        )
        assert len(docs) == 0

    def test_astronomer_populate_daily_task_metrics_feature_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"taskUsageMetricsEnabled": True}},
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-populate-daily-task-metrics.yaml",
            ],
        )

        assert len(docs) == 1
        assert docs[0]["kind"] == "CronJob"
        assert (
            docs[0]["metadata"]["name"]
            == "release-name-houston-populate-daily-task-metrics"
        )
        assert docs[0]["spec"]["schedule"] == "30 1 * * *"

    def test_houston_configmap_with_taskusagemetrics_enabled(self, kube_version):
        """Validate the houston configmap and its embedded data with
        taskUsageMetricsEnabled."""

        docs = render_chart(
            values={"global": {"taskUsageMetricsEnabled": True}},
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )

        doc = docs[0]
        prod_yaml = yaml.safe_load(doc["data"]["production.yaml"])
        assert prod_yaml["deployments"]["taskUsageMetricsEnabled"] is True
