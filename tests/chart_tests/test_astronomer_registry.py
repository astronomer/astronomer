from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import jmespath


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestRegistryStatefulset:
    def test_astronomer_registry_statefulset(self, kube_version):
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

    def test_astronomer_registry_statefulset_with_customenv(self, kube_version):
        """Test that helm renders statefulset template for astronomer
        registry with custom env values."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "registry": {
                        "extraEnv": [{"name": "REGISTRY_ENV_STORAGE", "value": "test"}]
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/registry/registry-statefulset.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert {"name": "REGISTRY_ENV_STORAGE", "value": "test"} in doc["spec"][
            "template"
        ]["spec"]["containers"][0]["env"]
