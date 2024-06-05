import pytest
from tests import get_cronjob_containerspec_by_name, supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonCronjobJob:
    def test_houston_cleanup_deployment_cronjob_defaults(self, kube_version):
        """Test cleanup deployments cronjob defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-deployments-cronjob.yaml"
            ],
        )
        assert len(docs) == 1
        c_by_name = get_cronjob_containerspec_by_name(docs[0])
        assert docs[0]["kind"] == "CronJob"
        assert docs[0]["metadata"]["name"] == "release-name-houston-cleanup-deployments"
        assert docs[0]["spec"]["schedule"] == "0 0 * * *"

        assert c_by_name["cleanup"]["args"] == [
            "yarn",
            "cleanup-deployments",
            "--",
            "--older-than=14",
            "--dry-run=false",
            "--canary=false",
        ]

        assert c_by_name["cleanup"]["securityContext"] == {"runAsNonRoot": True}

    def test_houston_cleanup_deployment_cronjob_overrides(self, kube_version):
        """Test cleanup deployments cronjob overrides."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "securityContext": {"allowPriviledgeEscalation": False},
                    "houston": {
                        "cleanupDeployments": {
                            "enabled": True,
                            "schedule": "22 5 * * *",
                            "olderThan": 30,
                        }
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-deployments-cronjob.yaml"
            ],
        )
        assert len(docs) == 1
        c_by_name = get_cronjob_containerspec_by_name(docs[0])
        assert docs[0]["kind"] == "CronJob"
        assert docs[0]["metadata"]["name"] == "release-name-houston-cleanup-deployments"
        assert docs[0]["spec"]["schedule"] == "22 5 * * *"

        assert c_by_name["cleanup"]["args"] == [
            "yarn",
            "cleanup-deployments",
            "--",
            "--older-than=30",
            "--dry-run=false",
            "--canary=false",
        ]

        assert c_by_name["cleanup"]["securityContext"] == {
            "runAsNonRoot": True,
            "allowPriviledgeEscalation": False,
        }

    def test_houston_cleanup_deployment_cronjob_disabled(self, kube_version):
        """Test cleanup deployments cronjob disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "cleanupDeployments": {"enabled": False},
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-cleanup-deployments-cronjob.yaml"
            ],
        )
        assert len(docs) == 0

    def test_houston_expire_deployment_cronjob_defaults(self, kube_version):
        """Test expire deployments cronjob defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-expire-deployments-cronjob.yaml"
            ],
        )
        assert len(docs) == 0

    def test_houston_expire_deployment_cronjob_enabled(self, kube_version):
        """Test expire deployments cronjob defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "expireDeployments": {
                            "enabled": True,
                        }
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-expire-deployments-cronjob.yaml"
            ],
        )
        assert len(docs) == 1
        c_by_name = get_cronjob_containerspec_by_name(docs[0])
        assert docs[0]["kind"] == "CronJob"
        assert docs[0]["metadata"]["name"] == "release-name-houston-expire-deployments"
        assert docs[0]["spec"]["schedule"] == "0 0 * * *"

        assert c_by_name["expire-deployments"]["args"] == [
            "yarn",
            "expire-deployments",
            "--",
            "--dry-run=false",
            "--canary=false",
        ]

        assert c_by_name["expire-deployments"]["securityContext"] == {
            "runAsNonRoot": True
        }

    def test_houston_expire_deployment_cronjob_overrides(self, kube_version):
        """Test expire deployments cronjob overrides."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "securityContext": {"allowPriviledgeEscalation": False},
                    "houston": {
                        "expireDeployments": {"enabled": True, "schedule": "22 5 * * *"}
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/cronjobs/houston-expire-deployments-cronjob.yaml"
            ],
        )
        assert len(docs) == 1
        c_by_name = get_cronjob_containerspec_by_name(docs[0])
        assert docs[0]["kind"] == "CronJob"
        assert docs[0]["metadata"]["name"] == "release-name-houston-expire-deployments"
        assert docs[0]["spec"]["schedule"] == "22 5 * * *"

        assert c_by_name["expire-deployments"]["args"] == [
            "yarn",
            "expire-deployments",
            "--",
            "--dry-run=false",
            "--canary=false",
        ]

        assert c_by_name["expire-deployments"]["securityContext"] == {
            "runAsNonRoot": True,
            "allowPriviledgeEscalation": False,
        }
