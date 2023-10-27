from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import jmespath


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
            show_only=[
                "charts/astronomer/templates/registry/registry-statefulset.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert any(
            "quay.io/astronomer/ap-registry:" in item
            for item in jmespath.search("spec.template.spec.containers[*].image", doc)
        )
        assert docs[0]["spec"]["template"]["spec"]["securityContext"] == {
            "fsGroup": 1000,
            "runAsGroup": 1000,
            "runAsUser": 1000,
        }

    def test_astronomer_registry_statefulset_with_custom_env(self, kube_version):
        """Test that helm renders statefulset template for astronomer
        registry with custom env values."""
        extra_env = {"name": "TEST_ENV_VAR_876", "value": "test"}
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"registry": {"extraEnv": [extra_env]}}},
            show_only=[
                "charts/astronomer/templates/registry/registry-statefulset.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert extra_env in doc["spec"]["template"]["spec"]["containers"][0]["env"]

    def test_astronomer_registry_statefulset_with_serviceaccount_enabled_defaults(
        self, kube_version
    ):
        """Test that helm renders statefulset and serviceAccount template for astronomer
        registry with SA enabled."""
        annotation = {
            "eks.amazonaws.com/role-arn": "custom-role",
        }
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "registry": {
                        "serviceAccount": {"create": True, "annotations": annotation}
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
        assert (
            doc["spec"]["template"]["spec"]["serviceAccountName"]
            == "release-name-registry"
        )

        doc = docs[1]
        assert doc["kind"] == "ServiceAccount"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert annotation == doc["metadata"]["annotations"]

    def test_astronomer_registry_statefulset_with_serviceaccount_enabled_with_custom_name(
        self, kube_version
    ):
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
        assert (
            doc["spec"]["template"]["spec"]["serviceAccountName"]
            == "release-name-customregistrysa"
        )

        doc = docs[1]
        assert doc["kind"] == "ServiceAccount"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-customregistrysa"
        assert annotation == doc["metadata"]["annotations"]

    def test_astronomer_registry_statefulset_with_serviceaccount_disabled(
        self, kube_version
    ):
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
        assert "serviceAccountName" not in docs[0]["spec"]["template"]["spec"]

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

    
    @pytest.mark.skip(reason="This test needs rework")
    def test_astronomer_registry_statefulset_with_podSecurityContext_disabled(
        self, kube_version
    ):
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
