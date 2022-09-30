from tests.chart_tests.helm_template_generator import render_chart
import pytest
from subprocess import CalledProcessError


def test_astronomer_bootstrap_secret_defaults():
    """Test the astronomer-bootstrap secret with defaults."""
    with pytest.raises(CalledProcessError):
        render_chart(
            show_only="charts/postgresql/templates/astronomer-bootstrap-secret.yaml"
        )


def test_astronomer_bootstrap_secret_postgres_enabled():
    """Test the astronomer-bootstrap secret with postgresEnabled = True"""
    docs = render_chart(
        show_only="charts/postgresql/templates/astronomer-bootstrap-secret.yaml",
        values={"global": {"postgresqlEnabled": True}},
    )

    assert docs == [
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "astronomer-bootstrap"},
            "data": {
                "connection": "cG9zdGdyZXM6Ly9wb3N0Z3Jlczpwb3N0Z3Jlc0ByZWxlYXNlLW5hbWUtcG9zdGdyZXNxbC5kZWZhdWx0LnN2Yy5jbHVzdGVyLmxvY2FsOjU0MzI="
            },
        }
    ]
