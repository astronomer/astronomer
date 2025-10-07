from pathlib import Path

import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestCommanderJWKSHookJob:
    def test_jwks_hook_job_defaults_data_plane(self, kube_version):
        """Test JWKS Hook Job defaults on data plane."""

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}, "astronomer": {"commander": {"serviceAccount": {"create": True}}}},
            show_only=sorted(
                [
                    str(x.relative_to(git_root_dir))
                    for x in Path(f"{git_root_dir}/charts/astronomer/templates/commander/jwks-hooks").glob("*")
                ]
            ),
        )

        for doc in docs:
            match doc["kind"]:
                case "Job":
                    job_doc = doc
                case "ServiceAccount":
                    sa_doc = doc
                case "Role":
                    role_doc = doc
                case "RoleBinding":
                    rolebinding_doc = doc
                case "ConfigMap":
                    configmap_doc = doc
                case _:
                    print(f"Unhandled kind {doc['kind']}")

        assert len(docs) == 5
        assert job_doc["metadata"]["name"] == "release-name-commander-jwks-hook"

        annotations = job_doc["metadata"]["annotations"]
        assert annotations["helm.sh/hook"] == "pre-install,pre-upgrade"
        assert annotations["helm.sh/hook-weight"] == "-1"
        assert annotations["helm.sh/hook-delete-policy"] == "before-hook-creation,hook-succeeded,hook-failed"
        assert annotations["astronomer.io/commander-sync"] == "platform-release=release-name"

        c_by_name = get_containers_by_name(job_doc)
        assert "commander-jwks-hook" in c_by_name

        container = c_by_name["commander-jwks-hook"]
        assert container["command"] == ["/bin/sh", "-c", "update-ca-certificates;python3 /scripts/commander-jwks.py"]
        assert container["resources"] == {
            "requests": {"cpu": "250m", "memory": "1Gi"},
            "limits": {"cpu": "500m", "memory": "2Gi"},
        }

        env_vars = get_env_vars_dict(container["env"])
        assert env_vars["CONTROL_PLANE_ENDPOINT"] == "https://houston.example.com"
        assert env_vars["SECRET_NAME"] == "release-name-houston-jwt-signing-certificate"
        assert env_vars["RETRY_ATTEMPTS"] == "2"
        assert env_vars["RETRY_DELAY"] == "10"

        assert sa_doc["metadata"]["name"] == "release-name-commander-jwks-hook-sa"

        assert role_doc["metadata"]["name"] == "release-name-commander-jwks-role"

        assert rolebinding_doc["metadata"]["name"] == "release-name-commander-jwks-binding"
        assert rolebinding_doc["subjects"][0]["name"] == "release-name-commander-jwks-hook-sa"
        assert rolebinding_doc["roleRef"]["name"] == "release-name-commander-jwks-role"

        assert configmap_doc["metadata"]["name"] == "release-name-commander-jwks-hook-config"
        assert "commander-jwks.py" in configmap_doc["data"]

    def test_jwks_hook_job_disabled_control_plane(self, kube_version):
        """Test JWKS Hook Job is not rendered on control plane."""

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=["charts/astronomer/templates/commander/jwks-hooks/commander-jwks-hooks.yaml"],
        )

        assert len(docs) == 0

    def test_jwks_hook_job_with_extra_env(self, kube_version):
        """Test JWKS Hook Job with extra environment variables."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "astronomer": {
                    "commander": {
                        "serviceAccount": {"create": True},
                        "jwksHook": {
                            "extraEnv": [
                                {"name": "CUSTOM_SOMETHING1", "value": "RANDOM_VALUE1"},
                                {"name": "CUSTOM_SOMETHING2", "value": "RANDOM_VALUE2"},
                            ]
                        },
                    }
                },
            },
            show_only=sorted(
                [
                    str(x.relative_to(git_root_dir))
                    for x in Path(f"{git_root_dir}/charts/astronomer/templates/commander/jwks-hooks").glob("*")
                ]
            ),
        )
        job_doc = None
        for doc in docs:
            if doc["kind"] == "Job":
                job_doc = doc
                break

        assert job_doc is not None
        c_by_name = get_containers_by_name(job_doc)
        container = c_by_name["commander-jwks-hook"]
        env_vars = get_env_vars_dict(container["env"])
        assert env_vars["CONTROL_PLANE_ENDPOINT"] == "https://houston.example.com"
        assert env_vars["SECRET_NAME"] == "release-name-houston-jwt-signing-certificate"
        assert env_vars["RETRY_ATTEMPTS"] == "2"
        assert env_vars["RETRY_DELAY"] == "10"

        assert env_vars["CUSTOM_SOMETHING1"] == "RANDOM_VALUE1"
        assert env_vars["CUSTOM_SOMETHING2"] == "RANDOM_VALUE2"

    def test_jwks_hook_job_with_extra_ca_certs(self, kube_version):
        """Test JWKS Hook Job with extra CA certs."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                    "privateCaCerts": [
                        "private-ca-cert-foo",
                        "private-ca-cert-bar",
                    ],
                },
            },
            show_only=["charts/astronomer/templates/commander/jwks-hooks/commander-jwks-hooks.yaml"],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "Job"
        c_by_name = get_containers_by_name(docs[0], include_init_containers=False)
        assert docs[0]["kind"] == "Job"
        assert docs[0]["metadata"]["name"] == "release-name-commander-jwks-hook"

        volumemounts = c_by_name["commander-jwks-hook"]["volumeMounts"]
        volumes = docs[0]["spec"]["template"]["spec"]["volumes"]

        expected_volumes = [
            {"name": "jwks-script", "configMap": {"name": "release-name-commander-jwks-hook-config", "defaultMode": 493}},
            {"name": "private-ca-cert-foo", "secret": {"secretName": "private-ca-cert-foo"}},
            {"name": "private-ca-cert-bar", "secret": {"secretName": "private-ca-cert-bar"}},
        ]

        expected_volumemounts = [
            {"name": "jwks-script", "mountPath": "/scripts"},
            {
                "name": "private-ca-cert-foo",
                "mountPath": "/usr/local/share/ca-certificates/private-ca-cert-foo.pem",
                "subPath": "cert.pem",
            },
            {
                "name": "private-ca-cert-bar",
                "mountPath": "/usr/local/share/ca-certificates/private-ca-cert-bar.pem",
                "subPath": "cert.pem",
            },
        ]

        assert volumemounts == expected_volumemounts
        assert volumes == expected_volumes
