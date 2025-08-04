import jmespath
import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


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
        assert doc["metadata"]["name"] == "release-name-registry"
        expected_env = {
            "name": "REGISTRY_NOTIFICATIONS_ENDPOINTS_0_HEADERS",
            "valueFrom": {
                "secretKeyRef": {
                    "name": "release-name-registry-auth-key",
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
                "astronomer": {"registry": {"gcs": {"useKeyfile": True, "enabled": True}}},
            },
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-registry"
        assert sorted(x["name"] for x in doc["spec"]["template"]["spec"]["volumes"]) == [
            "config",
            "data",
            "etc-ssl-certs",
            "gcs-keyfile",
            "jwks-certificate",
        ]
        assert sorted(x["name"] for x in doc["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]) == [
            "config",
            "data",
            "etc-ssl-certs",
            "gcs-keyfile",
            "jwks-certificate",
        ]

    def test_registry_sts_with_registry_persistence_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={"astronomer": {"registry": {"s3": {"enabled": True}}}},
        )

        assert docs[0]["kind"] == "Deployment"
        assert {"name": "data", "emptyDir": {}} in docs[0]["spec"]["template"]["spec"]["volumes"]

    def test_registry_sts_with_registry_s3_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={"astronomer": {"registry": {"s3": {"enabled": True}}}},
        )

        assert docs[0]["kind"] == "Deployment"
        assert {"name": "data", "emptyDir": {}} in docs[0]["spec"]["template"]["spec"]["volumes"]

    def test_registry_sts_with_registry_gcs_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={"astronomer": {"registry": {"gcs": {"enabled": True}}}},
        )

        assert docs[0]["kind"] == "Deployment"
        assert {"name": "data", "emptyDir": {}} in docs[0]["spec"]["template"]["spec"]["volumes"]

    def test_registry_sts_with_registry_azure_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={"astronomer": {"registry": {"azure": {"enabled": True}}}},
        )

        assert docs[0]["kind"] == "Deployment"
        assert {"name": "data", "emptyDir": {}} in docs[0]["spec"]["template"]["spec"]["volumes"]

    def test_registry_sts_with_podlabels(self, kube_version):
        labels = {"foo-key": "foo-value", "bar-key": "bar-value"}
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={"astronomer": {"podLabels": labels}},
        )

        for k, v in labels.items():
            assert docs[0]["spec"]["template"]["metadata"]["labels"][k] == v

    def test_registry_privateca_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"privateCaCerts": ["private-root-ca"]}},
            show_only=["charts/astronomer/templates/registry/registry-statefulset.yaml"],
        )
        volume_mount_search_result = jmespath.search(
            "spec.template.spec.containers[*].volumeMounts[?name == 'private-root-ca']",
            docs[0],
        )
        volume_search_result = jmespath.search(
            "spec.template.spec.volumes[?name == 'private-root-ca']",
            docs[0],
        )
        expected_volume_mounts_result = [
            [
                {
                    "mountPath": "/usr/local/share/ca-certificates/private-root-ca.pem",
                    "name": "private-root-ca",
                    "subPath": "cert.pem",
                }
            ]
        ]
        expected_volume_result = [{"name": "private-root-ca", "secret": {"secretName": "private-root-ca"}}]

        assert docs[0]["kind"] == "StatefulSet"
        assert volume_mount_search_result == expected_volume_mounts_result
        assert volume_search_result == expected_volume_result
        assert {"name": "UPDATE_CA_CERTS", "value": "true"} in docs[0]["spec"]["template"]["spec"]["containers"][0]["env"]

    def test_registry_privateca_enabled_with_external_backend(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"privateCaCerts": ["private-root-ca"]},
                "astronomer": {"registry": {"s3": {"enabled": True}}},
            },
            show_only=["charts/astronomer/templates/registry/registry-statefulset.yaml"],
        )
        volume_mount_search_result = jmespath.search(
            "spec.template.spec.containers[*].volumeMounts[?name == 'private-root-ca']",
            docs[0],
        )
        volume_search_result = jmespath.search(
            "spec.template.spec.volumes[?name == 'private-root-ca']",
            docs[0],
        )
        expected_volume_mounts_result = [
            [
                {
                    "mountPath": "/usr/local/share/ca-certificates/private-root-ca.pem",
                    "name": "private-root-ca",
                    "subPath": "cert.pem",
                }
            ]
        ]
        expected_volume_result = [{"name": "private-root-ca", "secret": {"secretName": "private-root-ca"}}]
        assert docs[0]["kind"] == "Deployment"
        assert volume_mount_search_result == expected_volume_mounts_result
        assert volume_search_result == expected_volume_result
        assert {"name": "UPDATE_CA_CERTS", "value": "true"} in docs[0]["spec"]["template"]["spec"]["containers"][0]["env"]
