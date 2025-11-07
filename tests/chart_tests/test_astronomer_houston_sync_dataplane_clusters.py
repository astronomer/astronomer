import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerHoustonSyncDataplaneClustersCronJobs:
    def test_astronomer_sync_dataplane_clusters_cron_defaults(self, kube_version):
        """Test that cron job is not created when feature is disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"syncDataplaneClusters": {"enabled": False}}}},
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-sync-dataplane-clusters-cronjob.yaml",
            ],
        )
        assert len(docs) == 0

    def test_astronomer_sync_dataplane_clusters_cron_feature_enabled(self, kube_version):
        """Test that cron job is created with correct configuration when feature is enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"syncDataplaneClusters": {"enabled": True}}}},
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-sync-dataplane-clusters-cronjob.yaml",
            ],
        )

        assert len(docs) == 1

        doc = docs[0]
        assert doc["kind"] == "CronJob"
        assert doc["metadata"]["name"] == "release-name-houston-sync-dataplane-clusters"
        assert doc["metadata"]["labels"]["component"] == "houston-sync-dataplane-clusters"
        spec = doc["spec"]["jobTemplate"]["spec"]["template"]
        assert spec["metadata"]["labels"]["component"] == "houston-sync-dataplane-clusters"
        assert spec["metadata"]["labels"]["app"] == "houston-sync-dataplane-clusters"
        assert doc["spec"]["schedule"] == "0 * * * *"
        assert spec["spec"]["containers"][0]["securityContext"] == {"readOnlyRootFilesystem": True, "runAsNonRoot": True}

        # Verify container args
        c_by_name = get_containers_by_name(doc)
        assert c_by_name["sync-dataplane-clusters"]["args"] == ["yarn", "sync-dataplane-clusters"]

    def test_astronomer_sync_dataplane_clusters_cron_custom_schedule(self, kube_version):
        """Test that custom schedule is respected."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "syncDataplaneClusters": {
                            "enabled": True,
                            "schedule": "30 * * * *",
                        }
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-sync-dataplane-clusters-cronjob.yaml",
            ],
        )

        assert len(docs) == 1

        doc = docs[0]
        assert doc["kind"] == "CronJob"
        assert doc["metadata"]["name"] == "release-name-houston-sync-dataplane-clusters"
        assert doc["spec"]["schedule"] == "30 * * * *"
