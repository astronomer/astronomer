"""Tests for charts/prometheus-postgres-exporter/files/split-data-source-name.sh.

With secretsFromFiles on, that init container splits the exporter's connection string into the
user, password and URI files postgres_exporter reads (DATA_SOURCE_USER_FILE, _PASS_FILE and
_URI_FILE), splitting it as postgres_exporter's own parser, Go's net/url, splits
DATA_SOURCE_NAME. These run it with the system sh; in the pod it runs under the exporter image's
busybox.
"""

import shutil
import stat
import subprocess

import pytest

from tests import git_root_dir

SCRIPT = git_root_dir / "charts/prometheus-postgres-exporter/files/split-data-source-name.sh"
OUTPUTS = ("data_source_user", "data_source_password", "data_source_uri")

pytestmark = pytest.mark.skipif(not (shutil.which("sh") and shutil.which("awk")), reason="needs sh and awk")


def split(tmp_path, dsn):
    """Run the script on ``dsn`` (str or bytes); return the completed process and the files it wrote."""
    dsn_file = tmp_path / "data_source_name"
    dsn_file.write_bytes(dsn if isinstance(dsn, bytes) else dsn.encode())
    out = tmp_path / "out"
    out.mkdir()
    proc = subprocess.run(["sh", str(SCRIPT), str(dsn_file), str(out)], capture_output=True, text=True, check=False)
    return proc, {p.name: p.read_bytes() for p in out.iterdir()}


@pytest.mark.parametrize(
    "dsn,user,password,uri",
    [
        pytest.param(
            "postgres://postgres:abc123@release-name-postgresql.astronomer.svc.cluster.local.:5432",
            "postgres",
            "abc123",
            "release-name-postgresql.astronomer.svc.cluster.local.:5432",
            id="bundled-postgresql",
        ),
        pytest.param(
            "postgresql://svc:pw@db.example.com:6543/my%20db?sslmode=require&connect_timeout=5",
            "svc",
            "pw",
            "db.example.com:6543/my%20db?sslmode=require&connect_timeout=5",
            id="path-and-query-kept-as-written",
        ),
        pytest.param(
            "postgres://ex%3Apo%40rter:p%40ss%3Aw%2Frd%3F%23%25%C3%A9%2C@h:5432",
            "ex:po@rter",
            "p@ss:w/rd?#%é,",
            "h:5432",
            id="credentials-percent-decoded",
        ),
        pytest.param("postgres://user:p@ss:word@h:5432/db", "user", "p@ss:word", "h:5432/db", id="last-at-first-colon"),
        pytest.param("postgres://u:a+b@h", "u", "a+b", "h", id="plus-is-not-a-space"),
        pytest.param("postgres://u:p%20q@h", "u", "p q", "h", id="inner-space"),
        pytest.param("postgres://u:p@h:5432/db#fragment", "u", "p", "h:5432/db", id="fragment-dropped"),
        pytest.param("postgres://u@h:5432", "u", "", "h:5432", id="no-password"),
        pytest.param("postgres://u:p@[::1]:5432/db", "u", "p", "[::1]:5432/db", id="ipv6"),
        pytest.param("postgres://u:p@h:5432\n", "u", "p", "h:5432", id="trailing-newline-in-the-secret"),
    ],
)
def test_splits_the_connection_string(tmp_path, dsn, user, password, uri):
    proc, files = split(tmp_path, dsn)

    assert proc.returncode == 0, proc.stderr
    assert files == {
        "data_source_user": user.encode(),
        "data_source_password": password.encode(),
        "data_source_uri": uri.encode(),
    }
    # 0600: the exporter runs as the same user as the init container, and no one else may read them.
    for name in OUTPUTS:
        assert stat.S_IMODE((tmp_path / "out" / name).stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "dsn,message",
    [
        pytest.param("", "is missing or empty", id="empty-secret"),
        pytest.param("mysql://u:SECRETMARKER@h/db", "is not a postgres:// or postgresql:// URL", id="not-postgres"),
        pytest.param("host=h user=u password=SECRETMARKER", "is not a postgres:// or postgresql:// URL", id="key-value-dsn"),
        pytest.param("postgres://u:SECRETMARKER,x@h", "has a comma", id="comma"),
        pytest.param("postgres://u:SECRETMARKER%zz@h", "the password has an invalid percent-escape", id="bad-escape"),
        pytest.param("postgres://u:SECRETMARKER%4@h", "the password has an invalid percent-escape", id="truncated-escape"),
        pytest.param("postgres://u:SECRETMARKER%00@h", "the password has an invalid percent-escape", id="nul"),
        pytest.param("postgres://u%zz:SECRETMARKER@h", "the user has an invalid percent-escape", id="bad-user-escape"),
        pytest.param("postgres://u:%20SECRETMARKER@h", "starts or ends with whitespace", id="edge-whitespace"),
        pytest.param("postgres://u:SECRET\tMARKER@h", "has a control character", id="control-character"),
        pytest.param("postgres://h:5432/db", "has no user", id="no-user"),
        pytest.param("postgres://u:SECRETMARKER@/db", "has no host", id="no-host"),
    ],
)
def test_refuses_what_it_cannot_split_without_printing_it(tmp_path, dsn, message):
    proc, files = split(tmp_path, dsn)

    assert proc.returncode != 0
    assert message in proc.stderr
    assert "SECRETMARKER" not in proc.stderr + proc.stdout
    assert "MARKER" not in proc.stderr + proc.stdout
    assert files == {}


def test_success_prints_nothing_from_the_connection_string(tmp_path):
    proc, _files = split(tmp_path, "postgres://SECRETUSER:SECRETMARKER@secret-host.example.com:5432/secretdb?sslmode=require")

    assert proc.returncode == 0, proc.stderr
    assert "SECRET" not in proc.stdout + proc.stderr
    assert "secret" not in proc.stdout + proc.stderr
