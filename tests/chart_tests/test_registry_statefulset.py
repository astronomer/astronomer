import jmespath
import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestRegistryStatefulset:
    show_only = ["charts/astronomer/templates/registry/registry-statefulset.yaml"]
    # All registry resources that carry a name/label/selector derived from the naming helpers.
    naming_templates = [
        "charts/astronomer/templates/registry/registry-statefulset.yaml",
        "charts/astronomer/templates/registry/registry-service.yaml",
        "charts/astronomer/templates/registry/registry-ingress.yaml",
        "charts/astronomer/templates/registry/registry-networkpolicy.yaml",
    ]

    @staticmethod
    def _ingress_backend_service_name(doc):
        return doc["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]["name"]

    @staticmethod
    def _by_kind(docs):
        return {doc["kind"]: doc for doc in docs}

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
        c_by_name = get_containers_by_name(docs[0], include_init_containers=True)
        assert c_by_name["etc-ssl-certs-copier"]["name"] == "etc-ssl-certs-copier"
        assert c_by_name["etc-ssl-certs-copier"]["resources"] == {
            "limits": {"cpu": "500m", "memory": "1024Mi"},
            "requests": {"cpu": "250m", "memory": "512Mi"},
        }

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
            show_only=self.show_only,
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
            show_only=self.show_only,
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

    def test_registry_hostAliases_overrides(self, kube_version):
        hostAliasSpec = [{"ip": "127.0.0.1", "hostnames": ["registry.hostname.one"]}]
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {"registry": {"hostAliases": hostAliasSpec}},
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert spec["hostAliases"] == hostAliasSpec

    def test_registry_naming_defaults(self, kube_version):
        """Default naming across the statefulset, service, ingress and networkpolicy."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"perHostIngress": {"enabled": True}, "networkPolicy": {"enabled": True}}},
            show_only=self.naming_templates,
        )
        by_kind = self._by_kind(docs)

        sts = by_kind["StatefulSet"]
        assert sts["metadata"]["name"] == "release-name-registry"
        assert sts["spec"]["serviceName"] == "release-name-registry"
        assert sts["metadata"]["labels"]["component"] == "registry"
        assert sts["spec"]["selector"]["matchLabels"]["component"] == "registry"
        assert sts["spec"]["template"]["metadata"]["labels"]["component"] == "registry"
        assert sts["spec"]["template"]["metadata"]["labels"]["app"] == "registry"

        svc = by_kind["Service"]
        assert svc["metadata"]["name"] == "release-name-registry"
        assert svc["metadata"]["labels"]["component"] == "registry"
        assert svc["spec"]["selector"]["component"] == "registry"

        ingress = by_kind["Ingress"]
        assert ingress["metadata"]["name"] == "release-name-registry-ingress"
        assert ingress["metadata"]["labels"]["component"] == "registry-ingress"
        assert self._ingress_backend_service_name(ingress) == "release-name-registry"

        netpol = by_kind["NetworkPolicy"]
        assert netpol["metadata"]["name"] == "release-name-registry-policy"
        assert netpol["metadata"]["labels"]["component"] == "registry-policy"
        assert netpol["spec"]["podSelector"]["matchLabels"]["component"] == "registry"

    def test_registry_naming_name_override(self, kube_version):
        """registry nameOverride overrides across all registry components."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"perHostIngress": {"enabled": True}, "networkPolicy": {"enabled": True}},
                "astronomer": {"registry": {"nameOverride": "custom-registry"}},
            },
            show_only=self.naming_templates,
        )
        by_kind = self._by_kind(docs)

        sts = by_kind["StatefulSet"]
        # fullname falls back to "<release>-<name>" since the release name does not contain the override
        assert sts["metadata"]["name"] == "release-name-custom-registry"
        assert sts["spec"]["serviceName"] == "release-name-custom-registry"
        assert sts["metadata"]["labels"]["component"] == "custom-registry"
        assert sts["spec"]["selector"]["matchLabels"]["component"] == "custom-registry"
        assert sts["spec"]["template"]["metadata"]["labels"]["component"] == "custom-registry"
        assert sts["spec"]["template"]["metadata"]["labels"]["app"] == "custom-registry"

        svc = by_kind["Service"]
        # service name tracks the fullname so the ingress backend keeps resolving
        assert svc["metadata"]["name"] == "release-name-custom-registry"
        assert svc["metadata"]["labels"]["component"] == "custom-registry"
        assert svc["spec"]["selector"]["component"] == "custom-registry"

        ingress = by_kind["Ingress"]
        assert ingress["metadata"]["name"] == "release-name-custom-registry-ingress"
        assert ingress["metadata"]["labels"]["component"] == "custom-registry-ingress"
        assert self._ingress_backend_service_name(ingress) == "release-name-custom-registry"

        netpol = by_kind["NetworkPolicy"]
        # policy name and its own component label stay stable; the podSelector tracks the override
        assert netpol["metadata"]["name"] == "release-name-registry-policy"
        assert netpol["metadata"]["labels"]["component"] == "registry-policy"
        assert netpol["spec"]["podSelector"]["matchLabels"]["component"] == "custom-registry"

    def test_registry_naming_fullname_override(self, kube_version):
        """registry fullnameOverride drives every fullname-derived resource name.
        The statefulset, service, and ingress (plus its backend) all pick up the override;
        labels/selectors and the networkpolicy name are untouched.
        """
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"perHostIngress": {"enabled": True}, "networkPolicy": {"enabled": True}},
                "astronomer": {"registry": {"fullnameOverride": "my-registry"}},
            },
            show_only=self.naming_templates,
        )
        by_kind = self._by_kind(docs)

        sts = by_kind["StatefulSet"]
        assert sts["metadata"]["name"] == "my-registry"
        assert sts["spec"]["serviceName"] == "my-registry"
        assert sts["metadata"]["labels"]["component"] == "registry"
        assert sts["spec"]["selector"]["matchLabels"]["component"] == "registry"

        svc = by_kind["Service"]
        assert svc["metadata"]["name"] == "my-registry"
        assert svc["metadata"]["labels"]["component"] == "registry"

        ingress = by_kind["Ingress"]
        assert ingress["metadata"]["name"] == "my-registry-ingress"
        assert ingress["metadata"]["labels"]["component"] == "registry-ingress"
        assert self._ingress_backend_service_name(ingress) == "my-registry"

        netpol = by_kind["NetworkPolicy"]
        assert netpol["metadata"]["name"] == "release-name-registry-policy"
        assert netpol["spec"]["podSelector"]["matchLabels"]["component"] == "registry"
