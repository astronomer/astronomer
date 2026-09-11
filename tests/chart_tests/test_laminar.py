from pathlib import Path

import jmespath
import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


def _templates(subdir=""):
    root = Path(f"{git_root_dir}/charts/laminar/templates/{subdir}")
    return sorted(str(x.relative_to(git_root_dir)) for x in root.glob("**/*.yaml") if not x.name.startswith("_"))


LAMINAR_TEMPLATES = _templates()
LAMINAR_API_SERVER_TEMPLATES = _templates("apiserver")
LAMINAR_HYPEVISOR_TEMPLATES = _templates("hypervisor")
LAMINAR_HELM_HOOKS_TEMPLATES = _templates("helm-hooks")
LAMINAR_ENV_CONFIGMAP_TEMPLATE = "charts/laminar/templates/configmap.yaml"


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestLaminar:
    def test_laminar_disabled_by_default(self, kube_version):
        """Test that laminar is disabled by default."""
        docs = render_chart(kube_version=kube_version)

        laminar_docs = [
            doc for doc in docs if str(doc.get("metadata", {}).get("labels", {}).get("chart", "")).startswith("laminar-")
        ]
        assert not laminar_docs

    @pytest.mark.parametrize("plane_mode", ["control", "unified"])
    def test_laminar_gated_by_plane_mode(self, kube_version, plane_mode):
        """Test that laminar renders only when the plane is data/unified."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"laminar": {"enabled": True}, "plane": {"mode": plane_mode}}},
            show_only=LAMINAR_TEMPLATES,
        )

        if plane_mode == "control":
            assert len(docs) == 0
        else:
            assert len(docs) > 0

    @pytest.mark.parametrize("plane_mode", ["unified", "data"])
    def test_laminar_hypervisor_defaults_when_enabled(self, kube_version, plane_mode):
        """Test that laminar renders only when the plane is data or unified."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"laminar": {"enabled": True}, "plane": {"mode": plane_mode}}},
            show_only=[*LAMINAR_HYPEVISOR_TEMPLATES, LAMINAR_ENV_CONFIGMAP_TEMPLATE],
        )
        assert len(docs) == 11
        hypervisor_deployment = docs[0]
        assert hypervisor_deployment["apiVersion"] == "apps/v1"
        assert hypervisor_deployment["metadata"]["name"] == "release-name-hypervisor"
        assert hypervisor_deployment["spec"]["template"]["spec"]["serviceAccountName"] == "release-name-hypervisor"
        c_by_name = get_containers_by_name(hypervisor_deployment, include_init_containers=True)
        assert len(c_by_name) == 1
        assert c_by_name["hypervisor"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 65534,
        }
        assert c_by_name["hypervisor"]["resources"] == {
            "requests": {"cpu": "200m", "memory": "256Mi"},
            "limits": {"cpu": "1", "memory": "1Gi"},
        }
        hypervisor_service = docs[4]
        assert hypervisor_service["kind"] == "Service"
        assert hypervisor_service["metadata"]["name"] == "release-name-hypervisor"
        assert hypervisor_service["metadata"]["labels"] == {
            "app.kubernetes.io/component": "hypervisor",
            "chart": "laminar-0.12.0",
            "release": "release-name",
            "heritage": "Helm",
            "plane": plane_mode,
            "app.kubernetes.io/name": "hypervisor",
        }
        assert hypervisor_service["spec"]["type"] == "ClusterIP"
        assert hypervisor_service["spec"]["ports"] == [
            {
                "name": "http",
                "protocol": "TCP",
                "port": 8000,
                "targetPort": "http",
            },
        ]
        volume_mount_search_result = jmespath.search(
            "spec.template.spec.containers[*].volumeMounts[?name == 'laminar-env']",
            docs[0],
        )
        expected_hypervisor_volume_mounts_result = [
            [
                {
                    "mountPath": "/laminar.env",
                    "name": "laminar-env",
                    "subPath": "laminar.env",
                    "readOnly": True,
                }
            ]
        ]
        assert volume_mount_search_result == expected_hypervisor_volume_mounts_result

    @pytest.mark.parametrize("plane_mode", ["unified", "data"])
    def test_laminar_database_hook_job_defaults(self, kube_version, plane_mode):
        """Test that laminar renders only when the plane is data or unified."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"laminar": {"enabled": True}, "plane": {"mode": plane_mode}}},
            show_only=LAMINAR_HELM_HOOKS_TEMPLATES,
        )
        assert len(docs) == 4
        laminar_db = docs[0]
        assert laminar_db["apiVersion"] == "batch/v1"
        assert laminar_db["metadata"]["name"] == "release-name-laminar-bootstrapper"
        assert laminar_db["spec"]["template"]["spec"]["serviceAccountName"] == "release-name-laminar-bootstrapper"
        c_by_name = get_containers_by_name(laminar_db, include_init_containers=True)
        assert len(c_by_name) == 1
        assert c_by_name["laminar-bootstrapper"]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 65534,
        }
        assert c_by_name["laminar-bootstrapper"]["resources"] == {
            "requests": {"cpu": "400m", "memory": "256Mi"},
            "limits": {"cpu": "1", "memory": "1Gi"},
        }

    @pytest.mark.parametrize("plane_mode", ["unified", "data"])
    def test_laminar_database_hook_with_custom_secret(self, kube_version, plane_mode):
        """Test that laminar renders only when the plane is data or unified."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"laminar": {"enabled": True}, "plane": {"mode": plane_mode}},
                "laminar": {"databaseBootstrapper": {"backendSecretName": "my-secret"}},
            },
            show_only=[
                *LAMINAR_HELM_HOOKS_TEMPLATES,
                "charts/laminar/templates/hypervisor/hypervisor-deployment.yaml",
            ],
        )
        assert len(docs) == 1
        hypervisor_deployment = docs[0]
        c_by_name = get_containers_by_name(hypervisor_deployment)
        env_vars = get_env_vars_dict(c_by_name["hypervisor"]["env"])
        assert env_vars["LAMINAR_DATABASE_URL"].get("secretKeyRef") == {
            "name": "release-name-laminar-backend",
            "key": "connection",
        }
