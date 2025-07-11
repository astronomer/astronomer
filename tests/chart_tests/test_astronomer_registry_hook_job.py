from pathlib import Path

import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestRegistryJWKSHookJob:
    def test_jwks_hook_job_defaults_data_plane(self, kube_version):
        """Test JWKS Hook Job defaults on data plane."""

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}, "astronomer": {"registry": {"serviceAccount": {"create": True}}}},
            show_only=sorted(
                [
                    str(x.relative_to(git_root_dir))
                    for x in Path(f"{git_root_dir}/charts/astronomer/templates/registry/jwks-hooks").glob("*")
                ]
            ),
        )

        for doc in docs:
            if doc["kind"] == "Job":
                job_doc = doc
            elif doc["kind"] == "ServiceAccount":
                sa_doc = doc
            elif doc["kind"] == "Role":
                role_doc = doc
            elif doc["kind"] == "RoleBinding":
                rolebinding_doc = doc
            elif doc["kind"] == "ConfigMap":
                configmap_doc = doc

        assert len(docs) == 5
        assert job_doc["metadata"]["name"] == "release-name-registry-jwks-hook"
        assert job_doc["metadata"]["annotations"]["helm.sh/hook"] == "pre-install,pre-upgrade"
        assert job_doc["metadata"]["annotations"]["helm.sh/hook-weight"] == "-10"
        assert job_doc["metadata"]["annotations"]["helm.sh/hook-delete-policy"] == "before-hook-creation,hook-succeeded"

        annotations = job_doc["metadata"]["annotations"]
        assert annotations["helm.sh/hook"] == "pre-install,pre-upgrade"
        assert annotations["helm.sh/hook-weight"] == "-10"
        assert annotations["helm.sh/hook-delete-policy"] == "before-hook-creation,hook-succeeded"
        assert annotations["astronomer.io/commander-sync"] == "platform-release=release-name"

        c_by_name = get_containers_by_name(job_doc)
        assert "registry-jwks-hook" in c_by_name

        container = c_by_name["registry-jwks-hook"]
        assert container["command"] == ["python3"]
        assert container["args"] == ["/scripts/registry-jwks.py"]

        env_vars = {x["name"]: x["value"] for x in container["env"]}
        assert env_vars["CONTROL_PLANE_ENDPOINT"] == "https://example.com"
        assert env_vars["SECRET_NAME"] == "registry-jwt-secret"
        assert env_vars["RETRY_ATTEMPTS"] == "2"
        assert env_vars["RETRY_DELAY"] == "10"

        assert sa_doc["metadata"]["name"] == "release-name-registry-jwks-hook-sa"

        assert role_doc["metadata"]["name"] == "release-name-registry-jwks-role"

        assert rolebinding_doc["metadata"]["name"] == "release-name-registry-jwks-binding"
        assert rolebinding_doc["subjects"][0]["name"] == "release-name-registry-jwks-hook-sa"
        assert rolebinding_doc["roleRef"]["name"] == "release-name-registry-jwks-role"

        assert configmap_doc["metadata"]["name"] == "release-name-registry-jwks-hook-config"
        assert "fetch-jwks.py" in configmap_doc["data"]

    def test_jwks_hook_job_disabled_control_plane(self, kube_version):
        """Test JWKS Hook Job is not rendered on control plane."""

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=sorted(
                [
                    str(x.relative_to(git_root_dir))
                    for x in Path(f"{git_root_dir}/charts/astronomer/templates/registry/jwks-hooks").glob("*")
                ]
            ),
        )

        assert len(docs) == 0
