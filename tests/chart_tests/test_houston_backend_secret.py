import base64

import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

BACKEND_SECRET_FILE = "charts/astronomer/templates/houston/api/houston-backend-secret.yaml"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestHoustonBackendSecret:
    def test_houston_backend_secret_renders_with_connection_key(self, kube_version):
        """Test that the backend secret renders and contains a connection key.

        When no existing secret is found (the common case in helm template / CI),
        the template should fall back to a random placeholder value so the chart
        still renders correctly on first install.
        """
        docs = render_chart(
            kube_version=kube_version,
            show_only=[BACKEND_SECRET_FILE],
        )

        assert len(docs) == 1
        secret = docs[0]
        assert secret["kind"] == "Secret"
        assert secret["type"] == "Opaque"
        assert secret["metadata"]["name"] == "release-name-houston-backend"
        assert "connection" in secret["data"]
        # The value must be non-empty and valid base64
        connection_b64 = secret["data"]["connection"]
        assert connection_b64
        base64.b64decode(connection_b64)  # raises if not valid base64

    def test_houston_backend_secret_not_rendered_in_data_plane(self, kube_version):
        """Test that the backend secret is not rendered in data plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=[BACKEND_SECRET_FILE],
        )

        assert len(docs) == 0

    def test_houston_backend_secret_not_rendered_when_custom_secret_name_set(self, kube_version):
        """Test that the managed secret is suppressed when backendSecretName is provided."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"backendSecretName": "my-custom-secret"}}},
            show_only=[BACKEND_SECRET_FILE],
        )

        assert len(docs) == 0

    def test_houston_backend_secret_rendered_in_control_mode(self, kube_version):
        """Test that the backend secret renders in control plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=[BACKEND_SECRET_FILE],
        )

        assert len(docs) == 1
        assert docs[0]["kind"] == "Secret"
        assert "connection" in docs[0]["data"]
