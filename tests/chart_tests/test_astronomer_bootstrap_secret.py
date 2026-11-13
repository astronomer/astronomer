import base64
from subprocess import CalledProcessError

import pytest

from tests.utils.chart import render_chart


def test_astronomer_bootstrap_secret_defaults():
    """Test the astronomer-bootstrap secret with defaults."""
    with pytest.raises(CalledProcessError):
        render_chart(show_only="charts/postgresql/templates/astronomer-bootstrap-secret.yaml")


def test_astronomer_bootstrap_secret_postgres_enabled():
    """Test the astronomer-bootstrap secret with postgresEnabled = True.

    The host ends in a trailing dot (absolute FQDN) so resolvers query it directly rather than walking
    the pod's ndots:5 search list — some clients' DNS resolvers (e.g. pgbouncer's c-ares) fail the
    search-expansion path for this <5-dot in-cluster name. The base64 below decodes to
    ``postgres://postgres:postgres@release-name-postgresql.default.svc.cluster.local.:5432``.
    """
    docs = render_chart(
        show_only="charts/postgresql/templates/astronomer-bootstrap-secret.yaml",
        values={"global": {"postgresql": {"enabled": True}}},
    )

    assert docs == [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "astronomer-bootstrap"},
            "data": {
                "connection": "cG9zdGdyZXM6Ly9wb3N0Z3Jlczpwb3N0Z3Jlc0ByZWxlYXNlLW5hbWUtcG9zdGdyZXNxbC5kZWZhdWx0LnN2Yy5jbHVzdGVyLmxvY2FsLjo1NDMy"
            },
        }
    ]


@pytest.mark.parametrize(
    "pgbouncer_enabled,expected_connection",
    [
        (False, "postgres://postgres:postgres@release-name-postgresql.default.svc.cluster.example.net.:5432"),
        (True, "postgres://postgres:postgres@release-name-pgbouncer.default.svc.cluster.example.net.:6543"),
    ],
    ids=["postgresql", "pgbouncer"],
)
def test_astronomer_bootstrap_secret_honors_cluster_domain(pgbouncer_enabled, expected_connection):
    docs = render_chart(
        show_only="charts/postgresql/templates/astronomer-bootstrap-secret.yaml",
        values={
            "global": {
                "clusterDomain": "cluster.example.net",
                "postgresql": {"enabled": True},
                "pgbouncer": {"enabled": pgbouncer_enabled},
            }
        },
    )

    assert base64.b64decode(docs[0]["data"]["connection"]).decode() == expected_connection
