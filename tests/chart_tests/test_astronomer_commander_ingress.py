import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerCommanderIngress:
    def test_astronomer_commander_grpc_ingress_default(self, kube_version):
        """Test that helm renders a good GRPC ingress template for
        astronomer/commander in data plane mode."""
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

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Ingress"
        assert doc["metadata"]["labels"]["plane"] == "unified"

    def test_astronomer_commander_grpc_ingress_control_plane_mode(self, kube_version):
        """Test that helm does not render GRPC ingress template for control plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=["charts/astronomer/templates/commander/commander-grpc-ingress.yaml"],
        )

        assert len(docs) == 0

    def test_astronomer_commander_grpc_ingress_with_tls_secret(self, kube_version):
        """Test that helm renders GRPC ingress with TLS configuration when tlsSecret is provided."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}, "tlsSecret": "my-tls-secret", "baseDomain": "example.com"}},
            show_only=["charts/astronomer/templates/commander/commander-grpc-ingress.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert "tls" in doc["spec"]
        assert doc["spec"]["tls"][0]["secretName"] == "my-tls-secret"
        assert "commander.example.com" in doc["spec"]["tls"][0]["hosts"]

    def test_astronomer_commander_grpc_ingress_with_acme(self, kube_version):
        """Test that helm renders GRPC ingress with ACME TLS configuration."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}, "acme": True, "baseDomain": "example.com"}},
            show_only=["charts/astronomer/templates/commander/commander-grpc-ingress.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["metadata"]["annotations"]["kubernetes.io/tls-acme"] == "true"
        assert "tls" in doc["spec"]
        assert doc["spec"]["tls"][0]["secretName"] == "houston-tls"

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

    def test_astronomer_commander_grpc_ingress_with_auth_sidecar(self, kube_version):
        """Test that helm renders GRPC ingress with auth sidecar enabled."""
        extra_annotations = {"auth.sidecar/enabled": "true"}
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}, "authSidecar": {"enabled": True}, "extraAnnotations": extra_annotations}},
            show_only=["charts/astronomer/templates/commander/commander-grpc-ingress.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        annotations = doc["metadata"]["annotations"]
        assert annotations["auth.sidecar/enabled"] == "true"
        assert "nginx.ingress.kubernetes.io/backend-protocol" not in annotations

    def test_astronomer_commander_grpc_ingress_k8s_version_compatibility(self, kube_version):
        """Test that helm renders GRPC ingress with correct backend configuration based on k8s version."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/astronomer/templates/commander/commander-grpc-ingress.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        if kube_version >= "1.19.0":
            backend = doc["spec"]["rules"][0]["http"]["paths"][0]["backend"]
            assert "service" in backend
            assert backend["service"]["name"] == "release-name-commander"
            assert backend["service"]["port"]["name"] == "commander-grpc"
            assert doc["spec"]["rules"][0]["http"]["paths"][0]["pathType"] == "Prefix"
        else:
            backend = doc["spec"]["rules"][0]["http"]["paths"][0]["backend"]
            assert backend["serviceName"] == "release-name-commander"
            assert backend["servicePort"] == "commander-grpc"

    def test_astronomer_commander_metadata_ingress_default(self, kube_version):
        """Test that helm renders a good metadata ingress template for
        astronomer/commander in data plane mode."""
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

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Ingress"

    def test_astronomer_commander_metadata_ingress_control_plane_mode(self, kube_version):
        """Test that helm does not render metadata ingress template for control plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=["charts/astronomer/templates/commander/commander-metadata-ingress.yaml"],
        )

        assert len(docs) == 0

    def test_astronomer_commander_metadata_ingress_with_tls_secret(self, kube_version):
        """Test that helm renders metadata ingress with TLS configuration when tlsSecret is provided."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}, "tlsSecret": "my-tls-secret"}},
            show_only=["charts/astronomer/templates/commander/commander-metadata-ingress.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert "tls" in doc["spec"]
        assert doc["spec"]["tls"][0]["secretName"] == "my-tls-secret"

    def test_astronomer_commander_metadata_ingress_with_acme(self, kube_version):
        """Test that helm renders metadata ingress with ACME TLS configuration."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}, "acme": True}},
            show_only=["charts/astronomer/templates/commander/commander-metadata-ingress.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["metadata"]["annotations"]["kubernetes.io/tls-acme"] == "true"
        assert "tls" in doc["spec"]
        assert doc["spec"]["tls"][0]["secretName"] == "astronomer-tls"

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

    def test_astronomer_commander_metadata_ingress_with_auth_sidecar(self, kube_version):
        """Test that helm renders metadata ingress with auth sidecar enabled."""
        extra_annotations = {"auth.sidecar/metadata": "true"}
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}, "authSidecar": {"enabled": True}, "extraAnnotations": extra_annotations}},
            show_only=["charts/astronomer/templates/commander/commander-metadata-ingress.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        annotations = doc["metadata"]["annotations"]
        assert annotations["auth.sidecar/metadata"] == "true"

        assert "nginx.ingress.kubernetes.io/rewrite-target" not in annotations

    def test_astronomer_commander_metadata_ingress_k8s_version_compatibility(self, kube_version):
        """Test that helm renders metadata ingress with correct backend configuration based on k8s version."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/astronomer/templates/commander/commander-metadata-ingress.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        if kube_version >= "1.19.0":
            backend = doc["spec"]["rules"][0]["http"]["paths"][0]["backend"]
            assert "service" in backend
            assert backend["service"]["name"] == "release-name-commander"
            assert backend["service"]["port"]["name"] == "commander-http"
            assert doc["spec"]["rules"][0]["http"]["paths"][0]["pathType"] == "Prefix"
            assert doc["spec"]["rules"][0]["http"]["paths"][0]["path"] == "/metadata"
        else:
            backend = doc["spec"]["rules"][0]["http"]["paths"][0]["backend"]
            assert backend["serviceName"] == "release-name-commander"
            assert backend["servicePort"] == "commander-http"
            assert doc["spec"]["rules"][0]["http"]["paths"][0]["path"] == "/"

    def test_astronomer_commander_both_ingresses_rendered_together(self, kube_version):
        """Test that both GRPC and metadata ingresses are rendered together in data plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=[
                "charts/astronomer/templates/commander/commander-grpc-ingress.yaml",
                "charts/astronomer/templates/commander/commander-metadata-ingress.yaml",
            ],
        )

        assert len(docs) == 2

        grpc_ingress = None
        metadata_ingress = None

        for doc in docs:
            if doc["metadata"]["name"] == "release-name-commander-api-ingress":
                grpc_ingress = doc
            elif doc["metadata"]["name"] == "release-name-commander-metadata-ingress":
                metadata_ingress = doc

        assert grpc_ingress is not None
        assert metadata_ingress is not None

        assert grpc_ingress["metadata"]["labels"]["component"] == "api-ingress"
        assert metadata_ingress["metadata"]["labels"]["component"] == "metadata-ingress"
