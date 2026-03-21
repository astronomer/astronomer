import base64

import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestInternalServiceAuthSecret:
    show_only = ["charts/astronomer/templates/secrets/internal-service-auth-secret.yaml"]

    @pytest.mark.parametrize(
        "plane_mode,expected_count",
        [
            ("data", 1),
            ("unified", 1),
            ("control", 0),
        ],
    )
    def test_secret_rendered_by_plane_mode(self, kube_version, plane_mode, expected_count):
        """Secret should only render for data and unified plane modes."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": plane_mode}}},
            show_only=self.show_only,
        )
        assert len(docs) == expected_count
        if expected_count:
            doc = docs[0]
            assert doc["kind"] == "Secret"
            assert doc["apiVersion"] == "v1"
            assert doc["metadata"]["name"] == "release-name-internal-service-auth"
            assert doc["type"] == "Opaque"
            assert "token" in doc["data"]

    @pytest.mark.parametrize("plane_mode", ["data", "unified"])
    def test_secret_labels(self, kube_version, plane_mode):
        """Secret should have correct labels for each rendered plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": plane_mode}}},
            show_only=self.show_only,
        )
        assert len(docs) == 1
        labels = docs[0]["metadata"]["labels"]
        assert labels["component"] == "internal-service-auth"
        assert labels["tier"] == "astronomer"
        assert labels["release"] == "release-name"
        assert labels["plane"] == plane_mode

    def test_secret_with_user_provided_token(self, kube_version):
        """When a user provides a token, the secret data should contain it base64-encoded."""
        custom_token = "my-custom-shared-secret-token"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "unified"},
                    "internalServiceAuth": {"token": custom_token},
                },
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        raw = base64.b64decode(docs[0]["data"]["token"]).decode()
        assert raw == custom_token

    def test_secret_auto_generated_token_not_empty(self, kube_version):
        """When no token is provided, a non-empty token should be auto-generated."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=self.show_only,
        )
        assert len(docs) == 1
        token_b64 = docs[0]["data"]["token"]
        raw = base64.b64decode(token_b64).decode()
        assert len(raw) > 0


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestInternalServiceAuthCommanderMount:
    show_only = ["charts/astronomer/templates/commander/commander-deployment.yaml"]

    @pytest.mark.parametrize("plane_mode", ["data", "unified"])
    def test_commander_has_internal_service_auth_volume(self, kube_version, plane_mode):
        """Commander deployment should have the internal-service-auth secret volume."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": plane_mode}}},
            show_only=self.show_only,
        )
        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]

        volumes = {v["name"]: v for v in spec["volumes"]}
        assert "internal-service-auth" in volumes
        assert volumes["internal-service-auth"]["secret"]["secretName"] == "release-name-internal-service-auth"

    @pytest.mark.parametrize("plane_mode", ["data", "unified"])
    def test_commander_has_internal_service_auth_volume_mount(self, kube_version, plane_mode):
        """Commander container should mount the secret at the expected path as read-only."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": plane_mode}}},
            show_only=self.show_only,
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        vm_by_name = {m["name"]: m for m in c_by_name["commander"]["volumeMounts"]}
        assert "internal-service-auth" in vm_by_name
        assert vm_by_name["internal-service-auth"]["mountPath"] == "/etc/astronomer/internal-service-auth"
        assert vm_by_name["internal-service-auth"]["readOnly"] is True


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestInternalServiceAuthPilotMount:
    show_only = ["charts/astronomer/templates/pilot/pilot-deployment.yaml"]

    def test_pilot_has_internal_service_auth_volume(self, kube_version):
        """Pilot deployment should have the internal-service-auth secret volume."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "astronomer": {"pilot": {"enabled": True}},
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]

        volumes = {v["name"]: v for v in spec["volumes"]}
        assert "internal-service-auth" in volumes
        assert volumes["internal-service-auth"]["secret"]["secretName"] == "release-name-internal-service-auth"

    def test_pilot_has_internal_service_auth_volume_mount(self, kube_version):
        """Pilot container should mount the secret at the expected path as read-only."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "astronomer": {"pilot": {"enabled": True}},
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        vm_by_name = {m["name"]: m for m in c_by_name["pilot"]["volumeMounts"]}
        assert "internal-service-auth" in vm_by_name
        assert vm_by_name["internal-service-auth"]["mountPath"] == "/etc/astronomer/internal-service-auth"
        assert vm_by_name["internal-service-auth"]["readOnly"] is True

    def test_pilot_no_volume_when_disabled(self, kube_version):
        """Pilot deployment should not render at all when disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "astronomer": {"pilot": {"enabled": False}},
            },
            show_only=self.show_only,
        )
        assert len(docs) == 0
