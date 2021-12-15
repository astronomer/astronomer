from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestRegistryStatefulset:

    show_only = ["charts/astronomer/templates/registry/registry-statefulset.yaml"]

    def test_registry_sts_basic_cases(self, kube_version):
        """Test some things that should apply to all cases."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
        )
        assert len(docs) == 1

        doc = docs[0]

        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-registry"
        expected_env = {
            "name": "REGISTRY_NOTIFICATIONS_ENDPOINTS_0_HEADERS",
            "valueFrom": {
                "secretKeyRef": {
                    "name": "RELEASE-NAME-registry-auth-key",
                    "key": "authHeaders",
                }
            },
        }
        assert expected_env in doc["spec"]["template"]["spec"]["containers"][0]["env"]

    def test_registry_sts_use_keyfile(self, kube_version):
        """Test some things that should apply to all cases."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {"baseDomain": "example.com"},
                "astronomer": {
                    "registry": {"gcs": {"useKeyfile": True, "enabled": True}}
                },
            },
        )

        assert len(docs) == 1
        assert (
            docs[0]["spec"]["template"]["spec"]["volumes"][2]["name"] == "gcs-keyfile"
        )
