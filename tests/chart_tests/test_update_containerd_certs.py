"""Integration tests for the update-containerd-certs.py script.

These tests exercise the script logic against real GKE config.toml samples
in tests/data_files (containerd 1.x / GKE 1.32 and containerd 2.x / GKE 1.33).
"""

# Import the script as a module
import importlib.util
import shutil
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

DATA_FILES_DIR = Path(__file__).parent.parent / "data_files"
SCRIPT_PATH = Path(__file__).parent.parent.parent / "files" / "update-containerd-certs.py"

# Load the script module dynamically
spec = importlib.util.spec_from_file_location("update_containerd_certs", SCRIPT_PATH)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


@pytest.fixture
def containerd_env(tmp_path):
    """Set up a temporary containerd-like directory structure."""
    containerd_dir = tmp_path / "containerd"
    containerd_dir.mkdir()
    certs_dir = containerd_dir / "certs.d" / "registry.example.com"
    certs_dir.mkdir(parents=True)

    private_certs_dir = tmp_path / "private-ca-certs" / "my-ca"
    private_certs_dir.mkdir(parents=True)
    (private_certs_dir / "my-ca.pem").write_text("-----BEGIN CERTIFICATE-----\nFAKECERT\n-----END CERTIFICATE-----\n")

    return {
        "containerd_dir": containerd_dir,
        "certs_dir": certs_dir,
        "private_certs_dir": tmp_path / "private-ca-certs",
        "tmp_path": tmp_path,
    }


def _completed_process(stdout: str, *, returncode: int = 0, stderr: str = "") -> MagicMock:
    """Build a CompletedProcess-like mock for subprocess.run."""
    return MagicMock(stdout=stdout, returncode=returncode, stderr=stderr)


class TestValidateRegistryHost:
    """Tests for REGISTRY_HOST validation."""

    def test_accepts_typical_registry_hostname(self) -> None:
        script.validate_registry_host("registry.example.com")

    @pytest.mark.parametrize(
        "bad_host",
        [
            "",
            "   ",
            "registry/bad",
            "registry bad",
            "..evil",
            "toolong" + "x" * 300,
        ],
    )
    def test_rejects_invalid_host(self, bad_host: str) -> None:
        with pytest.raises(ValueError):
            script.validate_registry_host(bad_host)


class TestDetectContainerdVersion:
    """Tests for containerd version detection."""

    @pytest.fixture(autouse=True)
    def _nsenter_on_path(self, request):
        """Make `shutil.which("nsenter")` return a fake path for every test in
        this class by default. Individual tests that explicitly verify the
        preflight behaviour opt out by not relying on this fixture's state."""
        if request.node.name in {
            "test_raises_with_actionable_message_when_nsenter_missing",
            "test_proceeds_when_nsenter_on_path",
        }:
            yield
            return
        with patch.object(script.shutil, "which", return_value="/usr/bin/nsenter"):
            yield

    @patch("subprocess.run")
    def test_detects_containerd_1x(self, mock_run):
        mock_run.return_value = _completed_process(
            "containerd github.com/containerd/containerd 1.7.29 442cb34bda9a6a0fed82a2ca7cade05c5c749582",
        )
        assert script.detect_containerd_version() == 1

    @patch("subprocess.run")
    def test_detects_containerd_2x(self, mock_run):
        mock_run.return_value = _completed_process(
            "containerd github.com/containerd/containerd/v2 2.0.7 4ac6c20c7bbf8177f29e46bbdc658fec02ffb8ad",
        )
        assert script.detect_containerd_version() == 2

    def test_raises_with_actionable_message_when_nsenter_missing(self, caplog):
        """When nsenter is not on PATH, the preflight must fail fast with a
        message that tells operators what's wrong and where to look."""
        with patch.object(script.shutil, "which", return_value=None):
            with pytest.raises(RuntimeError, match="nsenter not available"):
                script.ensure_nsenter_available()

        combined = " ".join(record.getMessage() for record in caplog.records)
        assert "nsenter is not available on PATH" in combined
        assert "util-linux" in combined

    def test_proceeds_when_nsenter_on_path(self):
        """Preflight should not short-circuit when nsenter exists."""
        with patch.object(script.shutil, "which", return_value="/usr/bin/nsenter"):
            script.ensure_nsenter_available()

    @patch("subprocess.run")
    def test_raises_on_nonzero_exit(self, mock_run):
        mock_run.return_value = _completed_process("", returncode=126, stderr="Permission denied")
        with pytest.raises(RuntimeError, match="containerd --version failed"):
            script.detect_containerd_version()

    @patch("subprocess.run")
    def test_raises_on_unparseable_stdout(self, mock_run):
        mock_run.return_value = _completed_process("not a version string")
        with pytest.raises(RuntimeError, match="unrecognized containerd"):
            script.detect_containerd_version()


class TestConfigPathDetection:
    """Tests for config_path detection in config.toml."""

    def test_detects_config_path_present(self):
        config = textwrap.dedent("""\
            [plugins."io.containerd.grpc.v1.cri".registry]
              config_path = "/etc/containerd/certs.d"
        """)
        assert script.config_path_is_set(config) is True

    def test_detects_config_path_absent(self):
        config = (DATA_FILES_DIR / "gke_1_32_containerd_1x_config.toml").read_text()
        assert script.config_path_is_set(config) is False

    def test_detects_config_path_absent_gke_133(self):
        config = (DATA_FILES_DIR / "gke_1_33_containerd_2x_config.toml").read_text()
        assert script.config_path_is_set(config) is False


class TestGenerateHostsToml:
    """Tests for hosts.toml generation."""

    def test_generates_valid_hosts_toml(self):
        # Temporarily override module globals
        original_registry = script.REGISTRY_HOST
        original_certs_dir = script.CERTS_DIR
        try:
            script.REGISTRY_HOST = "registry.example.com"
            script.CERTS_DIR = Path("/etc/containerd/certs.d/registry.example.com")
            result = script.generate_hosts_toml()
            assert 'server = "https://registry.example.com"' in result
            assert '[host."https://registry.example.com"]' in result
            assert 'capabilities = ["pull", "resolve"]' in result
            assert "ca.crt" in result
        finally:
            script.REGISTRY_HOST = original_registry
            script.CERTS_DIR = original_certs_dir


class TestBackupConfigToml:
    """Tests for config.toml backup logic."""

    def test_creates_timestamped_and_stable_backup(self, containerd_env):
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml.write_text("original content")

        original_path = script.CONTAINERD_HOST_PATH
        original_config = script.CONFIG_TOML
        original_bak = script.CONFIG_TOML_BAK
        try:
            script.CONTAINERD_HOST_PATH = containerd_env["containerd_dir"]
            script.CONFIG_TOML = config_toml
            script.CONFIG_TOML_BAK = containerd_env["containerd_dir"] / "config.toml.bak"

            script.backup_config_toml()

            # Stable .bak should exist
            assert script.CONFIG_TOML_BAK.is_file()
            assert script.CONFIG_TOML_BAK.read_text() == "original content"

            # At least one timestamped backup should exist
            timestamped = list(containerd_env["containerd_dir"].glob("config.toml.bak.*"))
            assert len(timestamped) >= 1
            assert timestamped[0].read_text() == "original content"
        finally:
            script.CONTAINERD_HOST_PATH = original_path
            script.CONFIG_TOML = original_config
            script.CONFIG_TOML_BAK = original_bak

    def test_does_not_overwrite_stable_backup(self, containerd_env):
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml_bak = containerd_env["containerd_dir"] / "config.toml.bak"
        config_toml.write_text("new content")
        config_toml_bak.write_text("original content")

        original_path = script.CONTAINERD_HOST_PATH
        original_config = script.CONFIG_TOML
        original_bak = script.CONFIG_TOML_BAK
        try:
            script.CONTAINERD_HOST_PATH = containerd_env["containerd_dir"]
            script.CONFIG_TOML = config_toml
            script.CONFIG_TOML_BAK = config_toml_bak

            script.backup_config_toml()

            # Stable .bak should NOT be overwritten
            assert config_toml_bak.read_text() == "original content"
        finally:
            script.CONTAINERD_HOST_PATH = original_path
            script.CONFIG_TOML = original_config
            script.CONFIG_TOML_BAK = original_bak


class TestInjectConfigPath:
    """Tests for config_path injection into config.toml."""

    def test_injects_v2_plugin_namespace(self, containerd_env):
        fixture = DATA_FILES_DIR / "gke_1_33_containerd_2x_config.toml"
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml_bak = containerd_env["containerd_dir"] / "config.toml.bak"
        shutil.copy2(fixture, config_toml)
        shutil.copy2(fixture, config_toml_bak)

        original_config = script.CONFIG_TOML
        original_bak = script.CONFIG_TOML_BAK
        original_cert_path = script.CERT_CONFIG_PATH
        try:
            script.CONFIG_TOML = config_toml
            script.CONFIG_TOML_BAK = config_toml_bak
            script.CERT_CONFIG_PATH = "/etc/containerd/certs.d"

            with patch.object(script, "restart_containerd"):
                script.inject_config_path(containerd_version=2)

            result = config_toml.read_text()
            assert 'plugins."io.containerd.cri.v1.images".registry' in result
            assert 'config_path = "/etc/containerd/certs.d"' in result
        finally:
            script.CONFIG_TOML = original_config
            script.CONFIG_TOML_BAK = original_bak
            script.CERT_CONFIG_PATH = original_cert_path

    def test_injects_v1_plugin_namespace(self, containerd_env):
        fixture = DATA_FILES_DIR / "gke_1_32_containerd_1x_config.toml"
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml_bak = containerd_env["containerd_dir"] / "config.toml.bak"
        shutil.copy2(fixture, config_toml)
        shutil.copy2(fixture, config_toml_bak)

        original_config = script.CONFIG_TOML
        original_bak = script.CONFIG_TOML_BAK
        original_cert_path = script.CERT_CONFIG_PATH
        try:
            script.CONFIG_TOML = config_toml
            script.CONFIG_TOML_BAK = config_toml_bak
            script.CERT_CONFIG_PATH = "/etc/containerd/certs.d"

            with patch.object(script, "restart_containerd"):
                script.inject_config_path(containerd_version=1)

            result = config_toml.read_text()
            assert 'plugins."io.containerd.grpc.v1.cri".registry' in result
            assert 'config_path = "/etc/containerd/certs.d"' in result
        finally:
            script.CONFIG_TOML = original_config
            script.CONFIG_TOML_BAK = original_bak
            script.CERT_CONFIG_PATH = original_cert_path


class TestCopyCaCerts:
    """Tests for CA certificate copying."""

    def test_copies_pem_to_certs_dir(self, containerd_env):
        original_certs_dir = script.CERTS_DIR
        original_private_dir = script.PRIVATE_CA_CERTS_DIR
        try:
            script.CERTS_DIR = containerd_env["certs_dir"]
            script.PRIVATE_CA_CERTS_DIR = containerd_env["private_certs_dir"]

            script.copy_ca_certs()

            ca_crt = containerd_env["certs_dir"] / "ca.crt"
            assert ca_crt.is_file()
            assert "FAKECERT" in ca_crt.read_text()
        finally:
            script.CERTS_DIR = original_certs_dir
            script.PRIVATE_CA_CERTS_DIR = original_private_dir

    def test_handles_missing_private_certs_dir(self, tmp_path):
        original_certs_dir = script.CERTS_DIR
        original_private_dir = script.PRIVATE_CA_CERTS_DIR
        try:
            script.CERTS_DIR = tmp_path / "certs.d" / "registry"
            script.PRIVATE_CA_CERTS_DIR = tmp_path / "nonexistent"

            # Should not raise
            script.copy_ca_certs()
        finally:
            script.CERTS_DIR = original_certs_dir
            script.PRIVATE_CA_CERTS_DIR = original_private_dir
