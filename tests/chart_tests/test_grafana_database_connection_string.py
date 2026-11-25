"""Tests for charts/grafana/files/database-connection-string.sh.

The grafana container runs it before grafana's run.sh. It turns the Postgres URL in
GRAFANA_DATABASE_URL into a lib/pq key=value string with every value single-quoted, because
Grafana puts the password from GF_DATABASE_URL into that string unquoted, and lib/pq then drops
a backslash in it. These run it with the system sh; in the pod it runs under the ap-grafana
image's busybox.
"""

import shutil
import subprocess

import pytest

from tests import git_root_dir

SCRIPT = git_root_dir / "charts/grafana/files/database-connection-string.sh"
DB_ENV = ("GF_DATABASE_URL", "GF_DATABASE_TYPE", "GF_DATABASE_CONNECTION_STRING", "GRAFANA_DATABASE_URL")

pytestmark = pytest.mark.skipif(not (shutil.which("sh") and shutil.which("awk")), reason="needs sh and awk")


def run(url, **env):
    """Run the script on ``url`` with ``env`` set; return the process and the database env grafana would get."""
    proc = subprocess.run(
        ["sh", str(SCRIPT), "env", "-0"],
        env={"PATH": "/usr/bin:/bin", "GRAFANA_DATABASE_URL": url, **env},
        capture_output=True,
        check=False,
    )
    pairs = (item.split("=", 1) for item in proc.stdout.decode().split("\0") if item)
    return proc, {k: v for k, v in pairs if k in DB_ENV}


@pytest.mark.parametrize(
    "url,expected",
    [
        pytest.param(
            "postgres://postgres:abc123@release-name-postgresql.astronomer.svc.cluster.local.:5432/release_name_grafana",
            "user='postgres' host='release-name-postgresql.astronomer.svc.cluster.local.' port='5432' "
            "dbname='release_name_grafana' sslmode='disable' password='abc123'",
            id="bundled-postgresql",
        ),
        pytest.param(
            "postgres://u:LabTest%5Cz9Qx@h:5432/db",
            r"user='u' host='h' port='5432' dbname='db' sslmode='disable' password='LabTest\\z9Qx'",
            id="encoded-backslash",
        ),
        pytest.param(
            r"postgresql://u:Lab\z9@h/db",
            r"user='u' host='h' port='5432' dbname='db' sslmode='disable' password='Lab\\z9'",
            id="raw-backslash-and-postgresql-scheme",
        ),
        pytest.param(
            "postgres://u:it%27s%20a%20pw@h/db",
            r"user='u' host='h' port='5432' dbname='db' sslmode='disable' password='it\'s a pw'",
            id="single-quote-and-space",
        ),
        pytest.param(
            "postgres://ad%40min:p@ss:w%2Frd%25%29%2B%3C%3D%5B%C3%A9@h:6543/my%20db",
            "user='ad@min' host='h' port='6543' dbname='my db' sslmode='disable' password='p@ss:w/rd%)+<=[é'",
            id="last-at-first-colon-and-percent-decoding",
        ),
        pytest.param(
            "postgres://u:a+b@h/db",
            "user='u' host='h' port='5432' dbname='db' sslmode='disable' password='a+b'",
            id="plus-is-not-a-space-in-the-password",
        ),
        pytest.param(
            "postgres://u@[::1]/db#fragment",
            "user='u' host='::1' port='5432' dbname='db' sslmode='disable'",
            id="no-password-ipv6-fragment-dropped",
        ),
        pytest.param(
            "postgres://u:p@h:5432/db?sslmode=require&application_name=a+b%26c",
            "user='u' host='h' port='5432' dbname='db' sslmode='disable' password='p' "
            "sslmode='require' application_name='a b&c'",
            id="query-parameters-after-sslmode",
        ),
    ],
)
def test_builds_quoted_connection_string(url, expected):
    proc, env = run(url)

    assert proc.returncode == 0, proc.stderr
    assert env == {"GF_DATABASE_TYPE": "postgres", "GF_DATABASE_CONNECTION_STRING": expected}


def test_uses_grafana_ssl_settings():
    proc, env = run(
        "postgres://u:p@h/db",
        GF_DATABASE_SSL_MODE="verify-full",
        GF_DATABASE_CA_CERT_PATH="/certs/ca.crt",
        GF_DATABASE_CLIENT_CERT_PATH="/certs/tls.crt",
        GF_DATABASE_CLIENT_KEY_PATH="/certs/tls.key",
        GF_DATABASE_SSL_SNI="1",
    )

    assert proc.returncode == 0, proc.stderr
    assert env["GF_DATABASE_CONNECTION_STRING"] == (
        "user='u' host='h' port='5432' dbname='db' sslmode='verify-full' sslcert='/certs/tls.crt' "
        "sslkey='/certs/tls.key' sslrootcert='/certs/ca.crt' sslsni='1' password='p'"
    )


@pytest.mark.parametrize("url", ["mysql://u:p@h:3306/db", ""], ids=["mysql", "empty"])
def test_other_urls_go_to_grafana_unchanged(url):
    proc, env = run(url)

    assert proc.returncode == 0, proc.stderr
    assert env == ({"GF_DATABASE_URL": url} if url else {})


@pytest.mark.parametrize(
    "url,message",
    [
        pytest.param("postgres://u:p%zz@h/db", "the password has an invalid percent-escape", id="bad-escape"),
        pytest.param("postgres://u:p\n@h/db", "the database URL has a control character", id="control-character"),
    ],
)
def test_fails_without_printing_the_password(url, message):
    proc, env = run(url)

    assert proc.returncode == 1
    assert proc.stderr.decode() == f"grafana-database-connection-string: {message}\n"
    assert proc.stdout == b""
    assert env == {}
