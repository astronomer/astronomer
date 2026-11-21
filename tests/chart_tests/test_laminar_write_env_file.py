"""Tests for charts/laminar/files/write-laminar-env.sh.

With secretsFromFiles on, that init container writes laminar's laminar.env settings file: the
chart's own file, then the JWKS certificate as a laminar_jwks setting, because laminar has no
file setting for its JWKS. These run it with the system sh; in the pod it runs under the
laminar image's dash.
"""

import shutil
import stat
import subprocess

import pytest

from tests import git_root_dir

SCRIPT = git_root_dir / "charts/laminar/files/write-laminar-env.sh"
SETTINGS = "laminar_apply_custom_ddl=True\nlaminar_hypervisor__queued_task_second_threshold=480\n"
CERTIFICATE = "-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIUTEST+/=\nAbCd0123\n-----END CERTIFICATE-----\n"

pytestmark = pytest.mark.skipif(not shutil.which("sh"), reason="needs sh")


def write(tmp_path, settings=SETTINGS, certificate=CERTIFICATE, args=None):
    """Run the script; return the completed process and the output file's text, or None if none was written."""
    settings_file = tmp_path / "laminar.env"
    certificate_file = tmp_path / "LAMINAR_JWKS"
    output = tmp_path / "out" / "laminar.env"
    output.parent.mkdir()
    if settings is not None:
        settings_file.write_text(settings)
    if certificate is not None:
        certificate_file.write_text(certificate)
    argv = args if args is not None else [str(settings_file), str(certificate_file), str(output)]
    proc = subprocess.run(["sh", str(SCRIPT), *argv], capture_output=True, text=True, check=False)
    return proc, output.read_text() if output.exists() else None


def test_writes_the_settings_then_the_certificate(tmp_path):
    proc, written = write(tmp_path)

    assert proc.returncode == 0, proc.stderr
    assert written == SETTINGS + '\nlaminar_jwks="' + CERTIFICATE.rstrip("\n") + '"\n'
    # 0600: the app container runs as the same user as the init container, and no one else may read it.
    assert stat.S_IMODE((tmp_path / "out" / "laminar.env").stat().st_mode) == 0o600


def test_the_certificate_line_starts_a_line_after_settings_without_a_final_newline(tmp_path):
    proc, written = write(tmp_path, settings="laminar_apply_custom_ddl=True")

    assert proc.returncode == 0, proc.stderr
    assert written.startswith('laminar_apply_custom_ddl=True\nlaminar_jwks="-----BEGIN CERTIFICATE-----\n')


def test_the_certificate_is_written_last_so_it_wins_over_a_line_in_the_settings(tmp_path):
    """python-dotenv keeps the last value for a repeated key."""
    proc, written = write(tmp_path, settings=SETTINGS + 'laminar_jwks="an operator value"\n')

    assert proc.returncode == 0, proc.stderr
    assert written.rstrip("\n").endswith('laminar_jwks="' + CERTIFICATE.rstrip("\n") + '"')
    assert written.index("an operator value") < written.rindex("laminar_jwks=")


@pytest.mark.parametrize(
    "certificate",
    [
        pytest.param('-----BEGIN CERTIFICATE-----\nSECRET"MARKER\n', id="double-quote"),
        pytest.param("-----BEGIN CERTIFICATE-----\nSECRET\\MARKER\n", id="backslash"),
        pytest.param("-----BEGIN CERTIFICATE-----\nSECRET${MARKER}\n", id="dollar"),
    ],
)
def test_refuses_a_certificate_laminar_env_cannot_hold_without_printing_it(tmp_path, certificate):
    """Inside a double-quoted value python-dotenv expands escapes and ${...}; a PEM certificate holds neither."""
    proc, written = write(tmp_path, certificate=certificate)

    assert proc.returncode != 0
    assert "is not a PEM certificate" in proc.stderr
    assert "MARKER" not in proc.stdout + proc.stderr
    assert written is None


@pytest.mark.parametrize(
    "certificate,message",
    [(None, "is missing or empty"), ("", "is missing or empty")],
    ids=["missing", "empty"],
)
def test_refuses_a_missing_or_empty_certificate(tmp_path, certificate, message):
    proc, written = write(tmp_path, certificate=certificate)

    assert proc.returncode != 0
    assert message in proc.stderr
    assert written is None


def test_refuses_a_missing_settings_file(tmp_path):
    proc, written = write(tmp_path, settings=None)

    assert proc.returncode != 0
    assert "cannot read the settings file" in proc.stderr
    assert written is None


def test_refuses_the_wrong_number_of_arguments(tmp_path):
    proc, _written = write(tmp_path, args=["only-one"])

    assert proc.returncode != 0
    assert "usage:" in proc.stderr


def test_success_prints_nothing_from_the_certificate(tmp_path):
    proc, _written = write(tmp_path)

    assert proc.returncode == 0, proc.stderr
    assert "BEGIN CERTIFICATE" not in proc.stdout + proc.stderr
    assert "MIIB" not in proc.stdout + proc.stderr
