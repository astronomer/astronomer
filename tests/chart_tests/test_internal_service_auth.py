import base64

import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestClusterLocalServiceAuthSecret:
    show_only = ["charts/astronomer/templates/secrets/cluster-local-service-auth-secret.yaml"]

    @pytest.mark.parametrize(
        "plane_mode,expected_count",
        [
            ("data", 1),
            ("unified", 1),
            ("control", 0),
        ],
    )
    def test_secret_rendered_by_plane_mode(self, kube_version, plane_mode, expected_count):
        """Secret renders for data/unified plane modes with correct metadata, labels, and a non-empty auto-generated token."""
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
            assert doc["metadata"]["name"] == "release-name-cluster-local-service-auth"
            assert doc["type"] == "Opaque"
            assert "token" in doc["data"]

            token_raw = base64.b64decode(doc["data"]["token"]).decode()
            assert len(token_raw) > 0

            labels = doc["metadata"]["labels"]
            assert labels["component"] == "cluster-local-service-auth"
            assert labels["tier"] == "astronomer"
            assert labels["release"] == "release-name"
            assert labels["plane"] == plane_mode

    @pytest.mark.parametrize(
        "token,expected_token",
        [
            ("my-custom-shared-secret-token", "my-custom-shared-secret-token"),
            ("", None),
        ],
        ids=["user_provided", "auto_generated"],
    )
    def test_secret_token_value(self, kube_version, token, expected_token):
        """User-provided token is used verbatim; empty value produces a non-empty auto-generated token."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "unified"},
                    "clusterLocalServiceAuth": {"token": token},
                },
            },
            show_only=self.show_only,
        )
        assert len(docs) == 1
        raw = base64.b64decode(docs[0]["data"]["token"]).decode()
        if expected_token is not None:
            assert raw == expected_token
        else:
            assert len(raw) > 0


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestClusterLocalServiceAuthCommanderMount:
    show_only = ["charts/astronomer/templates/commander/commander-deployment.yaml"]

    @pytest.mark.parametrize("plane_mode", ["data", "unified"])
    def test_commander_has_cluster_local_service_auth_volume_and_mount(self, kube_version, plane_mode):
        """Commander deployment should have the secret volume mounted read-only at the expected path."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": plane_mode}}},
            show_only=self.show_only,
        )
        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]

        volumes = {v["name"]: v for v in spec["volumes"]}
        assert "cluster-local-service-auth" in volumes
        assert volumes["cluster-local-service-auth"]["secret"]["secretName"] == "release-name-cluster-local-service-auth"

        c_by_name = get_containers_by_name(docs[0])
        vm_by_name = {m["name"]: m for m in c_by_name["commander"]["volumeMounts"]}
        assert "cluster-local-service-auth" in vm_by_name
        assert vm_by_name["cluster-local-service-auth"]["mountPath"] == "/etc/astronomer/cluster-local-service-auth"
        assert vm_by_name["cluster-local-service-auth"]["readOnly"] is True


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestClusterLocalServiceAuthPilotMount:
    show_only = ["charts/astronomer/templates/pilot/pilot-deployment.yaml"]

    def test_pilot_has_cluster_local_service_auth_volume_and_mount(self, kube_version):
        """Pilot deployment should have the secret volume mounted read-only at the expected path."""
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
        assert "cluster-local-service-auth" in volumes
        assert volumes["cluster-local-service-auth"]["secret"]["secretName"] == "release-name-cluster-local-service-auth"

        c_by_name = get_containers_by_name(docs[0])
        vm_by_name = {m["name"]: m for m in c_by_name["pilot"]["volumeMounts"]}
        assert "cluster-local-service-auth" in vm_by_name
        assert vm_by_name["cluster-local-service-auth"]["mountPath"] == "/etc/astronomer/cluster-local-service-auth"
        assert vm_by_name["cluster-local-service-auth"]["readOnly"] is True
