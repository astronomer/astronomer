import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart

REFRESH_CP_CHART_VERSION_FILE = "charts/astronomer/templates/houston/helm-hooks/houston-cp-refresh-job.yaml"


def _ha_values(**overrides):
    """global.controlPlaneHA enabled with a valid globalBaseDomain, control plane."""
    cpha = {"enabled": True, "globalBaseDomain": "astro.example.com"}
    cpha.update(overrides)
    return {"global": {"plane": {"mode": "control"}, "controlPlaneHA": cpha}}


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonHookJob:
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

        assert c_by_name["wait-for-db"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 1000,
        }

        assert c_by_name["houston-bootstrapper"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 1000,
        }

        assert c_by_name["post-upgrade-job"]["args"] == [
            "yarn",
            "upgrade-deployments",
            "--",
            "--canary=false",
        ]

        assert c_by_name["post-upgrade-job"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 1000,
        }
        assert {
            "name": "houston-config-volume",
            "mountPath": "/houston/config/production.yaml",
            "subPath": "production.yaml",
        } in c_by_name["post-upgrade-job"]["volumeMounts"]
        assert {
            "name": "houston-config-volume",
            "mountPath": "/houston/config/local-production.yaml",
            "subPath": "local-production.yaml",
        } in c_by_name["post-upgrade-job"]["volumeMounts"]

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

        assert c_by_name["wait-for-db"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 1000,
        }

        assert c_by_name["houston-bootstrapper"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 1000,
        }

        assert c_by_name["houston-db-migrations-job"]["args"] == ["yarn", "migrate"]

        assert c_by_name["houston-db-migrations-job"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 1000,
        }
        assert {
            "name": "houston-config-volume",
            "mountPath": "/houston/config/production.yaml",
            "subPath": "production.yaml",
        } in c_by_name["houston-db-migrations-job"]["volumeMounts"]
        assert {
            "name": "houston-config-volume",
            "mountPath": "/houston/config/local-production.yaml",
            "subPath": "local-production.yaml",
        } in c_by_name["houston-db-migrations-job"]["volumeMounts"]
        assert "resources" in c_by_name["wait-for-db"]
        assert "resources" in c_by_name["houston-bootstrapper"]
        assert "resources" in c_by_name["houston-db-migrations-job"]

    def test_db_migration_job_has_hook_weight(self, kube_version):
        """Db Migration Job must have explicit hook weight 0 and correct hooks."""

        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/astronomer/templates/houston/helm-hooks/houston-db-migration-job.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        annotations = doc["metadata"].get("annotations", {})
        assert annotations.get("helm.sh/hook") == "pre-upgrade,post-install"
        assert annotations.get("helm.sh/hook-weight") == "0"
        assert annotations.get("helm.sh/hook-delete-policy") == "before-hook-creation"

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
        env_vars = {x["name"]: x.get("value", x.get("valueFrom")) for x in c_by_name["post-upgrade-job"]["env"]}
        assert env_vars["DATABASE__CONNECTION"] == {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}}
        assert env_vars["DATABASE_URL"] == {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}}
        assert env_vars["DEPLOYMENTS__DATABASE__CONNECTION"] == {"secretKeyRef": {"name": "afwbackend", "key": "connection"}}

    def test_upgrade_deployments_init_containers_disabled_with_custom_houston_secret_name(self, kube_version):
        """Test Upgrade Deployments Job Init Containers are disabled when custom houston secret name is passed."""

        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "upgradeDeployments": {"enabled": True},
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
        env_vars = {x["name"]: x.get("value", x.get("valueFrom")) for x in c_by_name["post-upgrade-job"]["env"]}
        assert env_vars["DATABASE__CONNECTION"] == {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}}
        assert env_vars["DATABASE_URL"] == {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}}
        assert env_vars["DEPLOYMENTS__DATABASE__CONNECTION"] == {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}}


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestRefreshCpChartVersionHookJob:
    """The CP chartVersion refresh post-upgrade hook (PINF-930)."""

    def test_defaults_on_control_plane(self, kube_version):
        """Rendered on a control plane (mirrors db-migration/upgrade-deployments): name, args, mount."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=[REFRESH_CP_CHART_VERSION_FILE],
        )

        assert len(docs) == 1
        assert docs[0]["kind"] == "Job"
        assert docs[0]["metadata"]["name"] == "release-name-houston-cp-refresh"

        c_by_name = get_containers_by_name(docs[0], include_init_containers=True)
        job = c_by_name["refresh-cp-chart-version-job"]
        assert job["args"] == ["yarn", "refresh-cp-chart-version"]
        assert job["securityContext"] == {"readOnlyRootFilesystem": True, "runAsNonRoot": True}
        assert {
            "name": "houston-config-volume",
            "mountPath": "/houston/config/production.yaml",
            "subPath": "production.yaml",
        } in job["volumeMounts"]

    def test_absent_on_data_plane(self, kube_version):
        """A data-plane render emits no refresh Job (no CP registry on the data plane)."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=[REFRESH_CP_CHART_VERSION_FILE],
        )
        assert docs == []

    def test_hook_weight_and_order(self, kube_version):
        """post-upgrade hook, ordered after the pre-upgrade db-migration job."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=[REFRESH_CP_CHART_VERSION_FILE],
        )

        assert len(docs) == 1
        annotations = docs[0]["metadata"].get("annotations", {})
        assert annotations.get("helm.sh/hook") == "post-upgrade"
        assert annotations.get("helm.sh/hook-weight") == "0"
        assert annotations.get("helm.sh/hook-delete-policy") == "before-hook-creation"

    def test_cp_id_env_mounted_in_ha(self, kube_version):
        """Under HA, CP_ID (from the cp-identity Secret) is wired so the script can resolve its CP."""
        docs = render_chart(
            kube_version=kube_version,
            values=_ha_values(),
            show_only=[REFRESH_CP_CHART_VERSION_FILE],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0], include_init_containers=True)
        env = get_env_vars_dict(c_by_name["refresh-cp-chart-version-job"].get("env", []))
        assert env.get("CP_ID") == {"secretKeyRef": {"name": "cp-identity", "key": "cp_id"}}

    def test_cp_id_env_absent_without_ha(self, kube_version):
        """Without HA there is no cp-identity Secret, so the script no-ops (no CP_ID wired)."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=[REFRESH_CP_CHART_VERSION_FILE],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0], include_init_containers=True)
        env = get_env_vars_dict(c_by_name["refresh-cp-chart-version-job"].get("env", []))
        assert "CP_ID" not in env
