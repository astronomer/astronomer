import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerCommanderIngress:
    def test_astronomer_commander_grpc_ingress_default(self, kube_version):
        """Test that helm renders a correct GRPC ingress template for astronomer/commander in data plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/astronomer/templates/commander/commander-grpc-ingress.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Ingress"
        assert doc["metadata"]["name"] == "release-name-commander-api-ingress"
        assert doc["metadata"]["labels"]["component"] == "api-ingress"
        assert doc["metadata"]["labels"]["plane"] == "data"

        annotations = doc["metadata"]["annotations"]
        assert annotations["nginx.ingress.kubernetes.io/backend-protocol"] == "GRPC"
        assert annotations["nginx.ingress.kubernetes.io/enable-http2"] == "true"
        assert annotations["kubernetes.io/ingress.class"] == "release-name-nginx"
        assert annotations["nginx.ingress.kubernetes.io/custom-http-errors"] == "404"
        assert annotations["nginx.ingress.kubernetes.io/proxy-buffer-size"] == "16k"

    def test_astronomer_commander_grpc_ingress_unified_mode(self, kube_version):
        """Test that helm renders GRPC ingress template for unified plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "unified"}}},
            show_only=["charts/astronomer/templates/commander/commander-grpc-ingress.yaml"],
        )
        assert len(docs) == 0

    def test_astronomer_commander_grpc_ingress_control_plane_mode(self, kube_version):
        """Test that helm does not render GRPC ingress template for control plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=["charts/astronomer/templates/commander/commander-grpc-ingress.yaml"],
        )
        assert len(docs) == 0

    def test_astronomer_commander_grpc_ingress_with_custom_annotations(self, kube_version):
        """Test that helm renders GRPC ingress with custom annotations."""
        custom_annotations = {"nginx.ingress.kubernetes.io/rate-limit": "100", "custom.annotation/test": "value"}
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "astronomer": {"commander": {"ingress": {"annotation": custom_annotations}}},
            },
            show_only=["charts/astronomer/templates/commander/commander-grpc-ingress.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        annotations = doc["metadata"]["annotations"]
        assert annotations["nginx.ingress.kubernetes.io/rate-limit"] == "100"
        assert annotations["custom.annotation/test"] == "value"

    def test_astronomer_commander_metadata_ingress_default(self, kube_version):
        """Test that helm renders a good metadata ingress template for astronomer/commander in data plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/astronomer/templates/commander/commander-metadata-ingress.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Ingress"
        assert doc["metadata"]["name"] == "release-name-commander-metadata-ingress"
        assert doc["metadata"]["labels"]["component"] == "metadata-ingress"
        assert doc["metadata"]["labels"]["plane"] == "dataplane"

        annotations = doc["metadata"]["annotations"]
        assert annotations["kubernetes.io/ingress.class"] == "release-name-nginx"
        assert annotations["nginx.ingress.kubernetes.io/custom-http-errors"] == "404"
        assert annotations["nginx.ingress.kubernetes.io/proxy-buffer-size"] == "16k"
        assert annotations["nginx.ingress.kubernetes.io/rewrite-target"] == "/metadata"

    def test_astronomer_commander_metadata_ingress_unified_mode(self, kube_version):
        """Test that helm renders metadata ingress template for unified plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "unified"}}},
            show_only=["charts/astronomer/templates/commander/commander-metadata-ingress.yaml"],
        )
        assert len(docs) == 0

    def test_astronomer_commander_metadata_ingress_control_plane_mode(self, kube_version):
        """Test that helm does not render metadata ingress template for control plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=["charts/astronomer/templates/commander/commander-metadata-ingress.yaml"],
        )
        assert len(docs) == 0

    def test_astronomer_commander_metadata_ingress_with_custom_annotations(self, kube_version):
        """Test that helm renders metadata ingress with custom annotations."""
        custom_annotations = {"nginx.ingress.kubernetes.io/rate-limit": "200", "custom.metadata/test": "metadata-value"}
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "astronomer": {"commander": {"ingress": {"annotation": custom_annotations}}},
            },
            show_only=["charts/astronomer/templates/commander/commander-metadata-ingress.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        annotations = doc["metadata"]["annotations"]
        assert annotations["nginx.ingress.kubernetes.io/rate-limit"] == "200"
        assert annotations["custom.metadata/test"] == "metadata-value"
