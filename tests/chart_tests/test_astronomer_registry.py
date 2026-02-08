from pathlib import Path

import jmespath
import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestRegistryStatefulset:
    def test_astronomer_registry_statefulset_defaults(self, kube_version):
        """Test that helm renders a good statefulset template for astronomer
        registry."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/registry/registry-statefulset.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert any(
            "quay.io/astronomer/ap-registry:" in item for item in jmespath.search("spec.template.spec.containers[*].image", doc)
        )
        assert doc["spec"]["template"]["spec"]["securityContext"] == {
            "fsGroup": 1000,
            "runAsGroup": 1000,
            "runAsUser": 1000,
        }
        assert {"emptyDir": {}, "name": "etc-ssl-certs"} in doc["spec"]["template"]["spec"]["volumes"]
        assert {
            "mountPath": "/etc/ssl/certs_copy",
            "name": "etc-ssl-certs",
        } in doc["spec"]["template"]["spec"]["initContainers"][0]["volumeMounts"]
        assert {
            "mountPath": "/etc/ssl/certs",
            "name": "etc-ssl-certs",
        } in doc["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]

    def test_astronomer_registry_statefulset_with_custom_env_and_images(self, kube_version):
        """Test that helm renders statefulset template for astronomer registry with custom env values and images."""
        extra_env = {"name": "TEST_ENV_VAR_876", "value": "test"}
        values = {
            "astronomer": {
                "registry": {"extraEnv": [extra_env]},
                "images": {"registry": {"repository": "some-custom-repository", "tag": "1.2.3-sunshine"}},
            },
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/astronomer/templates/registry/registry-statefulset.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert extra_env in doc["spec"]["template"]["spec"]["containers"][0]["env"]
        assert (
            "some-custom-repository:1.2.3-sunshine"
            == doc["spec"]["template"]["spec"]["containers"][0]["image"]
            == doc["spec"]["template"]["spec"]["initContainers"][0]["image"]
        )

    def test_astronomer_registry_statefulset_with_serviceaccount_enabled_defaults(self, kube_version):
        """Test that helm renders statefulset and serviceAccount template for astronomer
        registry with SA enabled."""
        annotation = {
            "eks.amazonaws.com/role-arn": "custom-role",
        }
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"registry": {"serviceAccount": {"create": True, "annotations": annotation}}}},
            show_only=[
                "charts/astronomer/templates/registry/registry-statefulset.yaml",
                "charts/astronomer/templates/registry/registry-serviceaccount.yaml",
            ],
        )
        assert len(docs) == 2
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert doc["spec"]["template"]["spec"]["serviceAccountName"] == "release-name-registry"

        doc = docs[1]
        assert doc["kind"] == "ServiceAccount"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert annotation == doc["metadata"]["annotations"]

    def test_astronomer_registry_statefulset_with_serviceaccount_enabled_with_custom_name(self, kube_version):
        """Test that helm renders statefulset and serviceAccount template for astronomer
        registry with SA enabled with custom name."""
        annotation = {
            "eks.amazonaws.com/role-arn": "custom-role",
        }
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "registry": {
                        "serviceAccount": {
                            "create": True,
                            "name": "customregistrysa",
                            "annotations": annotation,
                        }
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/registry/registry-statefulset.yaml",
                "charts/astronomer/templates/registry/registry-serviceaccount.yaml",
            ],
        )
        assert len(docs) == 2
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert doc["spec"]["template"]["spec"]["serviceAccountName"] == "customregistrysa"

        doc = docs[1]
        assert doc["kind"] == "ServiceAccount"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "customregistrysa"
        assert annotation == doc["metadata"]["annotations"]

    def test_astronomer_registry_statefulset_with_serviceaccount_disabled(self, kube_version):
        """Test that helm renders statefulset template for astronomer
        registry with SA disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/astronomer/templates/registry/registry-statefulset.yaml",
                "charts/astronomer/templates/registry/registry-serviceaccount.yaml",
            ],
        )
        assert len(docs) == 1
        assert "default" in docs[0]["spec"]["template"]["spec"]["serviceAccountName"]

    def test_astronomer_registry_statefulset_with_scc_disabled(self, kube_version):
        """Test that helm renders statefulset template for astronomer
        registry with SA disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/astronomer/templates/registry/registry-scc.yaml",
            ],
        )
        assert len(docs) == 0

    def test_astronomer_registry_statefulset_with_scc_enabled(self, kube_version):
        """Test that helm renders scc template for astronomer registry."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"registry": {"serviceAccount": {"create": True, "sccEnabled": True}}}},
            show_only=[
                "charts/astronomer/templates/registry/registry-scc.yaml",
            ],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "SecurityContextConstraints"
        assert docs[0]["apiVersion"] == "security.openshift.io/v1"
        assert docs[0]["metadata"]["name"] == "release-name-registry-anyuid"
        assert docs[0]["users"] == ["system:serviceaccount:default:release-name-registry"]

    @pytest.mark.skip(reason="This test needs rework")
    def test_astronomer_registry_statefulset_with_podSecurityContext_disabled(self, kube_version):
        """Test that helm renders statefulset template for astronomer
        registry with podSecurityContext disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"registry": {"podSecurityContext": []}}},
            show_only=[
                "charts/astronomer/templates/registry/registry-statefulset.yaml",
            ],
        )
        assert len(docs) == 1
        assert "securityContext" not in docs[0]["spec"]["template"]["spec"]

    def test_registry_statefulset_without_ssl_cert_mount(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"registry": {"enableInsecureAuth": True}}},
            show_only=["charts/astronomer/templates/registry/registry-statefulset.yaml"],
        )
        not_expected_volume_mount = [{"mountPath": "/etc/docker/ssl", "name": "certificate"}]
        assert docs[0]["kind"] == "StatefulSet"
        assert len(docs[0]["spec"]["template"]["spec"]["volumes"]) == 2
        assert docs[0]["spec"]["template"]["spec"]["containers"][0]["volumeMounts"][1] != not_expected_volume_mount

    @pytest.mark.parametrize("mode", ["data", "unified"])
    def test_astronomer_registry_statefulset_enabled_for_data_and_unified_mode(self, kube_version, mode):
        """Test that helm renders registry statefulset when global.plane.mode is 'data' or 'unified'."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": mode}}},
            show_only=["charts/astronomer/templates/registry/registry-statefulset.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-registry"

    def test_astronomer_registry_statefulset_disabled_for_control_mode(self, kube_version):
        """Test that helm does not render registry statefulset when global.plane.mode is 'control'."""
        registry_files = [
            str(x.relative_to(git_root_dir))
            for x in Path(f"{git_root_dir}/charts/astronomer/templates/registry").glob("*")
            if x.is_file()
        ]

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=sorted(registry_files),
        )

        assert len(docs) == 0
