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
            show_only=["charts/astronomer/templates/houston/helm-hooks/houston-au-strategy-job.yaml"],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert docs[0]["kind"] == "Job"
        assert docs[0]["metadata"]["name"] == "release-name-update-resource-strategy"

        assert c_by_name["post-upgrade-update-resource-strategy"]["args"] == ["update-deployments-resource-mode"]

        assert c_by_name["post-upgrade-update-resource-strategy"]["securityContext"] == {"runAsNonRoot": True}

        assert "resources" in c_by_name["post-upgrade-update-resource-strategy"]

    def test_upgrade_deployments_job_defaults(self, kube_version):
        """Test Upgrade Deployments Job defaults."""

        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/astronomer/templates/houston/helm-hooks/houston-upgrade-deployments-job.yaml"],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0], include_init_containers=True)
        assert docs[0]["kind"] == "Job"
        assert docs[0]["metadata"]["name"] == "release-name-houston-upgrade-deployments"

        assert c_by_name["wait-for-db"]["securityContext"] == {"runAsNonRoot": True}

        assert c_by_name["houston-bootstrapper"]["securityContext"] == {"runAsNonRoot": True}

        assert c_by_name["post-upgrade-job"]["args"] == [
            "yarn",
            "upgrade-deployments",
            "--",
            "--canary=false",
        ]

        assert c_by_name["post-upgrade-job"]["securityContext"] == {"runAsNonRoot": True}

    def test_upgrade_deployments_job_disabled(self, kube_version):
        """Test Upgrade Deployments Job when disabled."""

        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"upgradeDeployments": {"enabled": False}}}},
            show_only=["charts/astronomer/templates/houston/helm-hooks/houston-upgrade-deployments-job.yaml"],
        )

        assert len(docs) == 0

    def test_db_migration_job_defaults(self, kube_version):
        """Test Db Migration Job defaults."""

        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/astronomer/templates/houston/helm-hooks/houston-db-migration-job.yaml"],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0], include_init_containers=True)
        assert docs[0]["kind"] == "Job"
        assert docs[0]["metadata"]["name"] == "release-name-houston-db-migrations"

        assert c_by_name["wait-for-db"]["securityContext"] == {"runAsNonRoot": True}

        assert c_by_name["houston-bootstrapper"]["securityContext"] == {"runAsNonRoot": True}

        assert c_by_name["houston-db-migrations-job"]["args"] == ["yarn", "migrate"]

        assert c_by_name["houston-db-migrations-job"]["securityContext"] == {"runAsNonRoot": True}
        assert "resources" in c_by_name["wait-for-db"]
        assert "resources" in c_by_name["houston-bootstrapper"]
        assert "resources" in c_by_name["houston-db-migrations-job"]

    def test_db_migration_job_custom_resources(self, kube_version):
        """Test Db Migration Job with customer resources."""

        overrides = {
            "requests": {"cpu": "300m", "memory": "300Mi"},
            "limits": {"cpu": "700m", "memory": "700Mi"},
        }

        value = {"astronomer": {"houston": {"resources": overrides}}}

        docs_overridden = render_chart(
            kube_version=kube_version,
            values=value,
            show_only=["charts/astronomer/templates/houston/helm-hooks/houston-db-migration-job.yaml"],
        )
        assert len(docs_overridden) == 1
        c_by_name = get_containers_by_name(docs_overridden[0], include_init_containers=True)

        assert c_by_name["wait-for-db"]["resources"] == overrides
        assert c_by_name["houston-bootstrapper"]["resources"] == overrides
        assert c_by_name["houston-db-migrations-job"]["resources"] == overrides

    def test_db_migration_job_init_containers_disabled_with_custom_secret_name(self, kube_version):
        """Test Upgrade Deployments Job Init Containers are disabled when custom secret name is passed."""

        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "upgradeDeployments": {"enabled": True},
                        "airflowBackendSecretName": "afwbackend",
                        "backendSecretName": "houstonbackend",
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/helm-hooks/houston-db-migration-job.yaml"],
        )

        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert "initContainers" not in spec
        assert "default" == spec["serviceAccountName"]

    def test_upgrade_deployments_init_containers_disabled_with_custom_secret_name(self, kube_version):
        """Test Upgrade Deployments Job Init Containers are disabled when custom secret name is passed."""

        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "upgradeDeployments": {"enabled": True},
                        "airflowBackendSecretName": "afwbackend",
                        "backendSecretName": "houstonbackend",
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/helm-hooks/houston-upgrade-deployments-job.yaml"],
        )

        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert "initContainers" not in spec
        assert "default" == spec["serviceAccountName"]
        c_by_name = get_containers_by_name(docs[0], include_init_containers=True)
        assert {
            "name": "DATABASE__CONNECTION",
            "valueFrom": {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}},
        } in c_by_name["post-upgrade-job"]["env"]
        assert {
            "name": "DATABASE_URL",
            "valueFrom": {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}},
        } in c_by_name["post-upgrade-job"]["env"]
        assert {
            "name": "DEPLOYMENTS__DATABASE__CONNECTION",
            "valueFrom": {"secretKeyRef": {"name": "afwbackend", "key": "connection"}},
        } in c_by_name["post-upgrade-job"]["env"]
