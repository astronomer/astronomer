import base64

import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

BACKEND_SECRET_FILE = "charts/astronomer/templates/houston/api/houston-backend-secret.yaml"

BACKEND_CONNECTION_VALUES = {
    "backendSecretConnection": True,
    "backendConnection": {
        "user": "houston",
        "pass": "s3cr3t",
        "host": "pg.example.com",
        "port": 5432,
        "db": "houston",
    },
}


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

    def test_houston_backend_secret_builds_connection_from_backend_connection(self, kube_version):
        """Test that backendSecretConnection builds a usable URL from backendConnection.

        Regression test for APC-859. This clause used to be unreachable, because the
        template only rendered when backendConnection was empty, and its printf wrote
        the schema escape into the format string, so "%24default" was read as a
        width-24 %d verb and rendered "%!d(MISSING)".
        """
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": BACKEND_CONNECTION_VALUES}},
            show_only=[BACKEND_SECRET_FILE],
        )

        assert len(docs) == 1
        connection = base64.b64decode(docs[0]["data"]["connection"]).decode()
        assert connection == "postgresql://houston:s3cr3t@pg.example.com:5432/houston?schema=houston%24default"

    def test_houston_backend_secret_honours_custom_schema_name(self, kube_version):
        """Test that global.houston.schemaName reaches the connection URL."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"houston": {"schemaName": "public"}},
                "astronomer": {"houston": BACKEND_CONNECTION_VALUES},
            },
            show_only=[BACKEND_SECRET_FILE],
        )

        assert len(docs) == 1
        connection = base64.b64decode(docs[0]["data"]["connection"]).decode()
        assert connection.endswith("?schema=public")

    def test_houston_backend_secret_url_encodes_schema_name(self, kube_version):
        """Test that a schema name containing "$" is percent-encoded.

        Prisma reads the schema from this query parameter, so a literal "$" has to
        arrive as %24. The default name contains one, which is why this matters.
        """
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"houston": {"schemaName": "my$schema"}},
                "astronomer": {"houston": BACKEND_CONNECTION_VALUES},
            },
            show_only=[BACKEND_SECRET_FILE],
        )

        assert len(docs) == 1
        connection = base64.b64decode(docs[0]["data"]["connection"]).decode()
        assert connection.endswith("?schema=my%24schema")

    def test_houston_backend_secret_not_rendered_for_connection_without_opt_in(self, kube_version):
        """Test that backendConnection alone still suppresses the managed secret.

        Only backendSecretConnection opts into building the URL. Without it the
        template stays skipped, as it was before APC-859, so an install relying on
        the bootstrapper to write this secret is unaffected.
        """
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {"houston": {k: v for k, v in BACKEND_CONNECTION_VALUES.items() if k != "backendSecretConnection"}}
            },
            show_only=[BACKEND_SECRET_FILE],
        )

        assert len(docs) == 0
