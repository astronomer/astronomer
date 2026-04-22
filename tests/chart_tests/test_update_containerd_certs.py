"""Integration tests for the update-containerd-certs.py script.

These tests exercise the script logic against real GKE config.toml samples
in tests/data_files (containerd 1.x / GKE 1.32 and containerd 2.x / GKE 1.33).
"""

import importlib.util
import shutil
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

DATA_FILES_DIR = Path(__file__).parent.parent / "data_files"
SCRIPT_PATH = Path(__file__).parent.parent.parent / "files" / "update-containerd-certs.py"


@pytest.fixture
def script():
    """Load update-containerd-certs.py fresh for each test.

    Tests mutate module-level globals (CONFIG_TOML, CERTS_DIR, etc.) to point at
    tmp_path. A fresh module per test keeps those mutations from leaking between
    tests and removes the need for try/finally restore blocks.
    """
    spec = importlib.util.spec_from_file_location("update_containerd_certs", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    def test_accepts_typical_registry_hostname(self, script) -> None:
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
    def test_rejects_invalid_host(self, script, bad_host: str) -> None:
        with pytest.raises(ValueError):
            script.validate_registry_host(bad_host)


class TestDetectContainerdVersion:
    """Tests for containerd version detection."""

    @pytest.fixture(autouse=True)
    def _nsenter_on_path(self, request, script):
        """Make `shutil.which("nsenter")` return a fake path for every test in
        this class by default. Individual tests that explicitly verify the
        preflight behaviour opt out."""
        if request.node.name in {
            "test_raises_with_actionable_message_when_nsenter_missing",
            "test_proceeds_when_nsenter_on_path",
        }:
            yield
            return
        with patch.object(script.shutil, "which", return_value="/usr/bin/nsenter"):
            yield

    @patch("subprocess.run")
    def test_detects_containerd_1x(self, mock_run, script):
        mock_run.return_value = _completed_process(
            "containerd github.com/containerd/containerd 1.7.29 442cb34bda9a6a0fed82a2ca7cade05c5c749582",
        )
        assert script.detect_containerd_version() == 1

    @patch("subprocess.run")
    def test_detects_containerd_2x(self, mock_run, script):
        mock_run.return_value = _completed_process(
            "containerd github.com/containerd/containerd/v2 2.0.7 4ac6c20c7bbf8177f29e46bbdc658fec02ffb8ad",
        )
        assert script.detect_containerd_version() == 2

    def test_raises_with_actionable_message_when_nsenter_missing(self, script, caplog):
        """When nsenter is not on PATH, the preflight must fail fast with a
        message that tells operators what's wrong and where to look."""
        with patch.object(script.shutil, "which", return_value=None):
            with pytest.raises(RuntimeError, match="nsenter not available"):
                script.ensure_nsenter_available()

        combined = " ".join(record.getMessage() for record in caplog.records)
        assert "nsenter is not available on PATH" in combined
        assert "util-linux" in combined

    def test_proceeds_when_nsenter_on_path(self, script):
        """Preflight should not short-circuit when nsenter exists."""
        with patch.object(script.shutil, "which", return_value="/usr/bin/nsenter"):
            script.ensure_nsenter_available()

    @patch("subprocess.run")
    def test_raises_on_nonzero_exit(self, mock_run, script):
        mock_run.return_value = _completed_process("", returncode=126, stderr="Permission denied")
        with pytest.raises(RuntimeError, match="containerd --version failed"):
            script.detect_containerd_version()

    @patch("subprocess.run")
    def test_raises_on_unparseable_stdout(self, mock_run, script):
        mock_run.return_value = _completed_process("not a version string")
        with pytest.raises(RuntimeError, match="unrecognized containerd"):
            script.detect_containerd_version()


class TestConfigPathDetection:
    """Tests for config_path detection in config.toml."""

    def _write(self, tmp_path, content: str) -> Path:
        p = tmp_path / "config.toml"
        p.write_text(content)
        return p

    def test_detects_config_path_present_v1(self, script, tmp_path):
        config = self._write(
            tmp_path,
            textwrap.dedent("""\
                [plugins."io.containerd.grpc.v1.cri".registry]
                  config_path = "/etc/containerd/certs.d"
            """),
        )
        assert script.config_path_is_set(config, 1) is True

    def test_detects_config_path_present_v2(self, script, tmp_path):
        config = self._write(
            tmp_path,
            textwrap.dedent("""\
                [plugins."io.containerd.cri.v1.images".registry]
                  config_path = "/etc/containerd/certs.d"
            """),
        )
        assert script.config_path_is_set(config, 2) is True

    def test_v1_set_does_not_false_match_v2(self, script, tmp_path):
        """config_path under the 1.x namespace must not satisfy the 2.x check."""
        config = self._write(
            tmp_path,
            textwrap.dedent("""\
                [plugins."io.containerd.grpc.v1.cri".registry]
                  config_path = "/etc/containerd/certs.d"
            """),
        )
        assert script.config_path_is_set(config, 2) is False

    def test_ignores_config_path_in_comment(self, script, tmp_path):
        """A `config_path` substring inside a comment must not false-match."""
        config = self._write(
            tmp_path,
            textwrap.dedent("""\
                # config_path is intentionally not set here
                [plugins."io.containerd.cri.v1.images".registry]
                  other_key = "value"
            """),
        )
        assert script.config_path_is_set(config, 2) is False

    def test_detects_config_path_absent_gke_132(self, script):
        config = DATA_FILES_DIR / "gke_1_32_containerd_1x_config.toml"
        assert script.config_path_is_set(config, 1) is False

    def test_detects_config_path_absent_gke_133(self, script):
        config = DATA_FILES_DIR / "gke_1_33_containerd_2x_config.toml"
        assert script.config_path_is_set(config, 2) is False

    def test_raises_on_malformed_toml(self, script, tmp_path):
        config = self._write(tmp_path, "this is not [ valid toml")
        with pytest.raises(RuntimeError, match="cannot parse"):
            script.config_path_is_set(config, 2)


class TestGenerateHostsToml:
    """Tests for hosts.toml generation."""

    def test_single_ca(self, script):
        script.REGISTRY_HOST = "registry.example.com"
        result = script.generate_hosts_toml(
            [Path("/etc/containerd/certs.d/registry.example.com/my-ca.pem")]
        )
        assert 'server = "https://registry.example.com"' in result
        assert '[host."https://registry.example.com"]' in result
        assert 'capabilities = ["pull", "resolve"]' in result
        assert 'ca = ["/etc/containerd/certs.d/registry.example.com/my-ca.pem"]' in result

    def test_multiple_cas(self, script):
        script.REGISTRY_HOST = "registry.example.com"
        result = script.generate_hosts_toml(
            [
                Path("/etc/containerd/certs.d/registry.example.com/ca-one.pem"),
                Path("/etc/containerd/certs.d/registry.example.com/ca-two.pem"),
            ]
        )
        assert (
            'ca = ["/etc/containerd/certs.d/registry.example.com/ca-one.pem", '
            '"/etc/containerd/certs.d/registry.example.com/ca-two.pem"]'
        ) in result

    def test_empty_ca_list(self, script):
        """No CAs mounted → empty TOML list, still valid TOML."""
        script.REGISTRY_HOST = "registry.example.com"
        result = script.generate_hosts_toml([])
        assert "ca = []" in result


class TestBackupConfigToml:
    """Tests for config.toml backup logic."""

    def test_creates_timestamped_and_stable_backup(self, script, containerd_env):
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml.write_text("original content")

        script.CONTAINERD_HOST_PATH = containerd_env["containerd_dir"]
        script.CONFIG_TOML = config_toml
        script.CONFIG_TOML_BAK = containerd_env["containerd_dir"] / "config.toml.bak"

        script.backup_config_toml()

        assert script.CONFIG_TOML_BAK.is_file()
        assert script.CONFIG_TOML_BAK.read_text() == "original content"

        timestamped = list(containerd_env["containerd_dir"].glob("config.toml.bak.*"))
        assert len(timestamped) >= 1
        assert timestamped[0].read_text() == "original content"

    def test_does_not_overwrite_stable_backup(self, script, containerd_env):
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml_bak = containerd_env["containerd_dir"] / "config.toml.bak"
        config_toml.write_text("new content")
        config_toml_bak.write_text("original content")

        script.CONTAINERD_HOST_PATH = containerd_env["containerd_dir"]
        script.CONFIG_TOML = config_toml
        script.CONFIG_TOML_BAK = config_toml_bak

        script.backup_config_toml()

        assert config_toml_bak.read_text() == "original content"


class TestInjectConfigPath:
    """Tests for config_path injection into config.toml."""

    def _prepare(self, script, containerd_env, fixture: Path) -> tuple[Path, Path]:
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml_bak = containerd_env["containerd_dir"] / "config.toml.bak"
        shutil.copy2(fixture, config_toml)
        shutil.copy2(fixture, config_toml_bak)

        script.CONFIG_TOML = config_toml
        script.CONFIG_TOML_BAK = config_toml_bak
        script.CERT_CONFIG_PATH = "/etc/containerd/certs.d"
        return config_toml, config_toml_bak

    def test_injects_v2_plugin_namespace(self, script, containerd_env):
        config_toml, _ = self._prepare(
            script, containerd_env, DATA_FILES_DIR / "gke_1_33_containerd_2x_config.toml"
        )

        with patch.object(script, "restart_containerd"):
            script.inject_config_path(containerd_version=2)

        # The result must still parse as TOML, and the parsed tree must contain
        # config_path under the 2.x plugin namespace — regardless of which TOML
        # form the script chose to emit.
        import tomllib as _tomllib
        parsed = _tomllib.loads(config_toml.read_text())
        assert (
            parsed["plugins"]["io.containerd.cri.v1.images"]["registry"]["config_path"]
            == "/etc/containerd/certs.d"
        )

    def test_strips_legacy_mirrors_before_injecting_on_real_gke_132_config(
        self, script, containerd_env
    ):
        """GKE 1.32's default config.toml ships a
        `[plugins."io.containerd.grpc.v1.cri".registry.mirrors."docker.io"]`
        block. Containerd 2.x transposes that into its own `cri.v1.images`
        namespace and silently blanks `config_path` when both coexist — the
        exact failure mode observed on a live GKE 1.33 upgrade. Inject must
        strip the mirrors block so config_path actually takes effect."""
        config_toml, _ = self._prepare(
            script, containerd_env, DATA_FILES_DIR / "gke_1_32_containerd_1x_config.toml"
        )

        with patch.object(script, "restart_containerd") as mock_restart:
            script.inject_config_path(containerd_version=2)
            mock_restart.assert_called_once()

        import tomllib as _tomllib
        parsed = _tomllib.loads(config_toml.read_text())
        v2_reg = parsed["plugins"]["io.containerd.cri.v1.images"]["registry"]
        assert v2_reg["config_path"] == "/etc/containerd/certs.d"
        # The legacy mirrors block must be gone from BOTH namespaces so
        # containerd 2.x has nothing to transpose into the new namespace.
        v1_reg = parsed["plugins"]["io.containerd.grpc.v1.cri"].get("registry", {})
        assert "mirrors" not in v1_reg
        assert "mirrors" not in v2_reg

    def test_strips_legacy_mirrors_block_on_real_gke_133_config(
        self, script, containerd_env
    ):
        """The live failure from the cluster: GKE 1.33's config.toml also ships
        the grpc.v1.cri mirrors block. This test uses the 1.33 fixture to lock
        in the fix end-to-end."""
        config_toml, _ = self._prepare(
            script, containerd_env, DATA_FILES_DIR / "gke_1_33_containerd_2x_config.toml"
        )

        with patch.object(script, "restart_containerd"):
            script.inject_config_path(containerd_version=2)

        import tomllib as _tomllib
        parsed = _tomllib.loads(config_toml.read_text())
        v2_reg = parsed["plugins"]["io.containerd.cri.v1.images"]["registry"]
        assert v2_reg["config_path"] == "/etc/containerd/certs.d"
        assert "mirrors" not in v2_reg
        # The 1.x namespace (which containerd 2.x reads for legacy migration) is
        # now mirrors-free too.
        v1_reg = parsed["plugins"]["io.containerd.grpc.v1.cri"].get("registry", {})
        assert "mirrors" not in v1_reg

    def test_strips_mirrors_already_in_2x_namespace(self, script, containerd_env):
        """Same behaviour if the mirrors are already declared under the 2.x
        namespace (hypothetical future GKE config): we still strip them."""
        preexisting = textwrap.dedent("""\
            [plugins."io.containerd.cri.v1.images".registry.mirrors."docker.io"]
              endpoint = ["https://mirror.example.com"]
        """)
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml_bak = containerd_env["containerd_dir"] / "config.toml.bak"
        config_toml.write_text(preexisting)
        config_toml_bak.write_text(preexisting)

        script.CONFIG_TOML = config_toml
        script.CONFIG_TOML_BAK = config_toml_bak
        script.CERT_CONFIG_PATH = "/etc/containerd/certs.d"

        with patch.object(script, "restart_containerd"):
            script.inject_config_path(containerd_version=2)

        import tomllib as _tomllib
        parsed = _tomllib.loads(config_toml.read_text())
        v2_reg = parsed["plugins"]["io.containerd.cri.v1.images"]["registry"]
        assert v2_reg["config_path"] == "/etc/containerd/certs.d"
        assert "mirrors" not in v2_reg

    def test_no_op_when_config_path_already_set(self, script, containerd_env):
        """If config_path is already set under the correct namespace AND no
        legacy mirrors remain, injection is a true no-op (no restart, no file
        rewrite)."""
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml_bak = containerd_env["containerd_dir"] / "config.toml.bak"
        preexisting = textwrap.dedent("""\
            [plugins."io.containerd.cri.v1.images".registry]
              config_path = "/already/set"
        """)
        config_toml.write_text(preexisting)
        config_toml_bak.write_text(preexisting)

        script.CONFIG_TOML = config_toml
        script.CONFIG_TOML_BAK = config_toml_bak
        script.CERT_CONFIG_PATH = "/etc/containerd/certs.d"

        with patch.object(script, "restart_containerd") as mock_restart:
            script.inject_config_path(containerd_version=2)
            mock_restart.assert_not_called()

        assert config_toml.read_text() == preexisting

    def test_recovers_half_injected_state(self, script, containerd_env):
        """Reproducer for the live GKE 1.33 failure: a previous (pre-fix)
        deploy left config.toml with BOTH a `config_path` injection AND the
        legacy `grpc.v1.cri.registry.mirrors` block. containerd 2.x silently
        zeroes config_path in this state.

        The fix re-runs the injection on startup even when config_path is
        already set, as long as mirrors are still present. The result must be:
          * mirrors gone from both namespaces
          * config_path still set (no duplicate key)
          * containerd restarted so the reconciled config takes effect
        """
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml_bak = containerd_env["containerd_dir"] / "config.toml.bak"
        half_injected = textwrap.dedent("""\
            [plugins."io.containerd.grpc.v1.cri".registry.mirrors."docker.io"]
              endpoint = ["https://mirror.gcr.io"]
            [plugins."io.containerd.cri.v1.images".registry]
              config_path = "/etc/containerd/certs.d"
        """)
        config_toml.write_text(half_injected)
        config_toml_bak.write_text(half_injected)

        script.CONFIG_TOML = config_toml
        script.CONFIG_TOML_BAK = config_toml_bak
        script.CERT_CONFIG_PATH = "/etc/containerd/certs.d"

        with patch.object(script, "restart_containerd") as mock_restart:
            script.inject_config_path(containerd_version=2)
            # Reconciliation requires a restart — containerd needs to re-read
            # config.toml without the mirrors conflict for config_path to stick.
            mock_restart.assert_called_once()

        import tomllib as _tomllib
        parsed = _tomllib.loads(config_toml.read_text())
        v2_reg = parsed["plugins"]["io.containerd.cri.v1.images"]["registry"]
        assert v2_reg["config_path"] == "/etc/containerd/certs.d"
        assert "mirrors" not in v2_reg
        # Mirrors must be gone from the 1.x namespace too. In this fixture the
        # only thing under grpc.v1.cri was the mirrors block, so the whole
        # plugin namespace may disappear entirely — either is acceptable.
        v1_plugin = parsed.get("plugins", {}).get("io.containerd.grpc.v1.cri", {})
        v1_reg = v1_plugin.get("registry", {})
        assert "mirrors" not in v1_reg


def _wire_certs_dir(script, certs_dir: Path) -> None:
    """In tests, the container view and host view point at the same tmp path."""
    script.CERTS_DIR = certs_dir
    script.CERTS_DIR_CONTAINER = certs_dir
    script.CERTS_DIR_HOST = certs_dir


class TestCopyCaCerts:
    """Tests for CA certificate copying."""

    def test_copies_pem_to_certs_dir(self, script, containerd_env):
        _wire_certs_dir(script, containerd_env["certs_dir"])
        script.PRIVATE_CA_CERTS_DIR = containerd_env["private_certs_dir"]

        copied = script.copy_ca_certs()

        assert len(copied) == 1
        dest = containerd_env["certs_dir"] / "my-ca.pem"
        assert dest.is_file()
        assert "FAKECERT" in dest.read_text()
        assert copied == [dest]

    def test_handles_missing_private_certs_dir(self, script, tmp_path):
        _wire_certs_dir(script, tmp_path / "certs.d" / "registry")
        script.PRIVATE_CA_CERTS_DIR = tmp_path / "nonexistent"

        assert script.copy_ca_certs() == []

    def test_returns_empty_when_no_pems_present(self, script, tmp_path):
        """Directory exists but holds no PEMs — must no-op, not create empty files."""
        private_dir = tmp_path / "private-ca-certs"
        private_dir.mkdir()
        (private_dir / "empty-ca").mkdir()

        certs_dir = tmp_path / "certs.d" / "registry"
        _wire_certs_dir(script, certs_dir)
        script.PRIVATE_CA_CERTS_DIR = private_dir

        assert script.copy_ca_certs() == []
        assert not certs_dir.exists()

    def test_copies_each_ca_to_its_own_file(self, script, containerd_env):
        """Multiple mounted CA secrets must each land as a separate file so the
        directory reflects the full list — matches the docstring and the old
        shell-script behavior."""
        _wire_certs_dir(script, containerd_env["certs_dir"])
        script.PRIVATE_CA_CERTS_DIR = containerd_env["private_certs_dir"]

        second = containerd_env["private_certs_dir"] / "other-ca"
        second.mkdir()
        (second / "other-ca.pem").write_text(
            "-----BEGIN CERTIFICATE-----\nOTHERCERT\n-----END CERTIFICATE-----\n"
        )

        copied = script.copy_ca_certs()

        assert {p.name for p in copied} == {"my-ca.pem", "other-ca.pem"}
        assert "FAKECERT" in (containerd_env["certs_dir"] / "my-ca.pem").read_text()
        assert "OTHERCERT" in (containerd_env["certs_dir"] / "other-ca.pem").read_text()

    def test_return_order_is_deterministic(self, script, containerd_env):
        """Return order must be stable across runs so the main loop's
        checksum-based short-circuit can rely on it."""
        _wire_certs_dir(script, containerd_env["certs_dir"])
        script.PRIVATE_CA_CERTS_DIR = containerd_env["private_certs_dir"]

        second = containerd_env["private_certs_dir"] / "other-ca"
        second.mkdir()
        (second / "other-ca.pem").write_text(
            "-----BEGIN CERTIFICATE-----\nOTHERCERT\n-----END CERTIFICATE-----\n"
        )

        first_run = script.copy_ca_certs()
        second_run = script.copy_ca_certs()
        assert [p.name for p in first_run] == [p.name for p in second_run]


class TestStripRegistryMirrorsBlocks:
    """Unit tests for the mirrors-stripping helper.

    This is a substring surgery on config.toml source text. tomllib.dumps()
    doesn't exist in stdlib so we can't do a structural round-trip; the helper
    works with TOML section headers at the text level. These tests lock in the
    known shapes — primarily GKE's shipped `mirrors."docker.io"` block — and
    guard a few edge cases."""

    def test_noop_when_no_mirrors(self, script):
        src = textwrap.dedent("""\
            [plugins."io.containerd.cri.v1.images".registry]
              config_path = "/etc/containerd/certs.d"
        """)
        assert script._strip_registry_mirrors_blocks(src) == src

    def test_strips_single_mirrors_block_under_v1_namespace(self, script):
        src = textwrap.dedent("""\
            [plugins."io.containerd.grpc.v1.cri"]
              enable_cdi = true
            [plugins."io.containerd.grpc.v1.cri".registry.mirrors."docker.io"]
              endpoint = ["https://mirror.gcr.io","https://registry-1.docker.io"]
            [metrics]
              address = "127.0.0.1:1338"
        """)
        out = script._strip_registry_mirrors_blocks(src)
        assert "mirrors" not in out
        # Surrounding sections preserved.
        assert '[plugins."io.containerd.grpc.v1.cri"]' in out
        assert "[metrics]" in out
        # Body of the mirrors block (`endpoint = ...`) is gone.
        assert "mirror.gcr.io" not in out

    def test_strips_mirrors_block_under_v2_namespace(self, script):
        src = textwrap.dedent("""\
            [plugins."io.containerd.cri.v1.images".registry.mirrors."docker.io"]
              endpoint = ["https://mirror.example.com"]
            [something_else]
              key = "value"
        """)
        out = script._strip_registry_mirrors_blocks(src)
        assert "mirrors" not in out
        assert "mirror.example.com" not in out
        assert "[something_else]" in out

    def test_strips_multiple_mirrors_blocks(self, script):
        src = textwrap.dedent("""\
            [plugins."io.containerd.grpc.v1.cri".registry.mirrors."docker.io"]
              endpoint = ["https://a"]
            [plugins."io.containerd.grpc.v1.cri".registry.mirrors."quay.io"]
              endpoint = ["https://b"]
            [metrics]
              address = "127.0.0.1:1338"
        """)
        out = script._strip_registry_mirrors_blocks(src)
        assert "mirrors" not in out
        assert "[metrics]" in out

    def test_preserves_other_registry_subsections(self, script):
        """Only `mirrors.*` sections are stripped — `configs.*.tls` and sibling
        registry subsections must survive (important on 1.x customers using the
        inline-TLS pattern alongside mirrors)."""
        src = textwrap.dedent("""\
            [plugins."io.containerd.grpc.v1.cri".registry.mirrors."docker.io"]
              endpoint = ["https://mirror.gcr.io"]
            [plugins."io.containerd.grpc.v1.cri".registry.configs."example.com".tls]
              ca_file = "/path/to/ca.pem"
        """)
        out = script._strip_registry_mirrors_blocks(src)
        assert "mirrors" not in out
        assert "configs" in out
        assert "ca_file" in out


class TestWriteCustomerConfigToml:
    """Tests for the containerd 1.x operator-supplied-blob strategy.

    1.x no longer generates registry-trust TOML itself. It appends whatever the
    operator provides via `global.privateCaCertsAddToHost.containerdConfigToml`
    to config.toml (the pre-PINF-432 approach)."""

    _BLOB = textwrap.dedent("""\
        [plugins."io.containerd.grpc.v1.cri".registry.configs."registry.example.com".tls]
          ca_file = "/etc/containerd/certs.d/registry.example.com/my-ca.pem"
    """)

    def _prepare(self, script, containerd_env) -> tuple[Path, Path]:
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml_bak = containerd_env["containerd_dir"] / "config.toml.bak"
        shutil.copy2(DATA_FILES_DIR / "gke_1_32_containerd_1x_config.toml", config_toml)
        shutil.copy2(DATA_FILES_DIR / "gke_1_32_containerd_1x_config.toml", config_toml_bak)
        script.CONFIG_TOML = config_toml
        script.CONFIG_TOML_BAK = config_toml_bak
        return config_toml, config_toml_bak

    def test_appends_blob_and_parses_cleanly(self, script, containerd_env):
        """Happy path: the blob is appended and the combined file is valid TOML
        with the expected ca_file under the expected key path."""
        config_toml, _ = self._prepare(script, containerd_env)

        changed = script.write_customer_config_toml(self._BLOB)

        assert changed is True
        import tomllib as _tomllib
        parsed = _tomllib.loads(config_toml.read_text())
        v1 = parsed["plugins"]["io.containerd.grpc.v1.cri"]["registry"]
        tls = v1["configs"]["registry.example.com"]["tls"]
        assert tls["ca_file"].endswith("my-ca.pem")
        # GKE 1.32's mirrors block must survive
        assert "mirrors" in v1
        # config_path must NOT be written (we're in the 1.x inline-schema world
        # and combining mirrors with config_path breaks containerd)
        assert "config_path" not in v1

    def test_empty_blob_raises_with_actionable_message(self, script, containerd_env, caplog):
        """On 1.x the operator is expected to set containerdConfigToml. Running
        with an empty blob must fail loudly rather than silently doing nothing."""
        self._prepare(script, containerd_env)

        with pytest.raises(RuntimeError, match="required on containerd 1.x"):
            script.write_customer_config_toml("")

        combined = " ".join(r.getMessage() for r in caplog.records)
        assert "containerdConfigToml" in combined
        assert "GKE 1.33" in combined

    def test_invalid_toml_raises_and_leaves_file_untouched(self, script, containerd_env):
        """Syntactically broken blob must not be written (containerd would fail
        to start). config.toml must remain exactly as before the call."""
        config_toml, _ = self._prepare(script, containerd_env)
        original = config_toml.read_text()

        with pytest.raises(RuntimeError, match="invalid TOML"):
            script.write_customer_config_toml("this is [[[not valid toml")

        assert config_toml.read_text() == original

    def test_idempotent_on_second_call(self, script, containerd_env):
        """Same blob twice → second call reports no change, so caller skips
        the containerd restart."""
        self._prepare(script, containerd_env)

        first = script.write_customer_config_toml(self._BLOB)
        second = script.write_customer_config_toml(self._BLOB)

        assert first is True
        assert second is False

    def test_changed_blob_triggers_rewrite(self, script, containerd_env):
        """Different blob value → reports change (caller will restart)."""
        self._prepare(script, containerd_env)

        other_blob = self._BLOB.replace("my-ca.pem", "rotated-ca.pem")

        script.write_customer_config_toml(self._BLOB)
        changed = script.write_customer_config_toml(other_blob)

        assert changed is True


class TestSourcePemChecksum:
    """Tests for the source-PEM change detector used by the main loop."""

    def test_empty_when_dir_missing(self, script, tmp_path):
        script.PRIVATE_CA_CERTS_DIR = tmp_path / "nonexistent"
        assert script.source_pem_checksum() == ""

    def test_stable_when_contents_unchanged(self, script, containerd_env):
        script.PRIVATE_CA_CERTS_DIR = containerd_env["private_certs_dir"]
        first = script.source_pem_checksum()
        second = script.source_pem_checksum()
        assert first and first == second

    def test_changes_when_pem_contents_change(self, script, containerd_env):
        script.PRIVATE_CA_CERTS_DIR = containerd_env["private_certs_dir"]
        before = script.source_pem_checksum()

        pem = next((containerd_env["private_certs_dir"] / "my-ca").glob("*.pem"))
        pem.write_text("-----BEGIN CERTIFICATE-----\nROTATED\n-----END CERTIFICATE-----\n")

        after = script.source_pem_checksum()
        assert before != after

    def test_changes_when_new_pem_added(self, script, containerd_env):
        script.PRIVATE_CA_CERTS_DIR = containerd_env["private_certs_dir"]
        before = script.source_pem_checksum()

        new_ca = containerd_env["private_certs_dir"] / "second-ca"
        new_ca.mkdir()
        (new_ca / "second-ca.pem").write_text("-----BEGIN CERTIFICATE-----\nNEW\n-----END CERTIFICATE-----\n")

        after = script.source_pem_checksum()
        assert before != after


class _StopLoop(Exception):
    """Sentinel used by end-to-end tests to break out of the main poll loop."""


class TestMainEndToEnd:
    """End-to-end tests that drive `main()` against real GKE config.toml fixtures.

    These exercise the whole startup sequence (version detect → parse config →
    inject config_path if missing → restart → first poll tick → hosts.toml write)
    and are the primary guard against regressions in the version-unification fix
    for PINF-432: both containerd 1.x and 2.x without config_path must inject
    under the correct plugin namespace and use the hosts.toml path.
    """

    @pytest.fixture
    def wired(self, script, containerd_env):
        """Point the script's module globals at the tmp containerd tree and stub
        out subprocess calls and the nsenter preflight. Returns a dict of paths
        the test can assert on."""
        config_toml = containerd_env["containerd_dir"] / "config.toml"
        config_toml_bak = containerd_env["containerd_dir"] / "config.toml.bak"

        script.REGISTRY_HOST = "registry.example.com"
        script.CONTAINERD_HOST_PATH = containerd_env["containerd_dir"]
        script.CONFIG_TOML = config_toml
        script.CONFIG_TOML_BAK = config_toml_bak
        script.CERT_CONFIG_PATH = "/etc/containerd/certs.d"
        _wire_certs_dir(script, containerd_env["certs_dir"])
        script.PRIVATE_CA_CERTS_DIR = containerd_env["private_certs_dir"]
        # Default: no customer blob. Tests that exercise the 1.x path override.
        script.CONTAINERD_CONFIG_TOML = ""

        return {
            "config_toml": config_toml,
            "config_toml_bak": config_toml_bak,
            "certs_dir": containerd_env["certs_dir"],
        }

    def _run_main_once(self, script, subprocess_stdout: str):
        """Drive main() through startup and exactly one poll iteration.

        Strategy: patch time.sleep to raise on its first call. main() only calls
        sleep at the bottom of the loop body (after hosts.toml has been written),
        so we observe the full post-inject steady state before bailing.
        """
        which_stub = "/usr/bin/nsenter"
        run_stub = _completed_process(subprocess_stdout)

        with patch.object(script.shutil, "which", return_value=which_stub), \
             patch.object(script, "restart_containerd") as mock_restart, \
             patch("subprocess.run", return_value=run_stub), \
             patch.object(script.time, "sleep", side_effect=_StopLoop):
            with pytest.raises(_StopLoop):
                script.main()
        return mock_restart

    def test_gke_132_containerd_1x_applies_customer_config_toml(self, script, wired):
        """On GKE 1.32 the script appends the operator-supplied TOML blob
        (from `global.privateCaCertsAddToHost.containerdConfigToml`) to
        config.toml. The script does not generate registry-trust TOML itself
        on 1.x — the operator owns the schema.

        This matches the pre-PINF-432 shell script's behaviour exactly; this
        e2e test is the regression guard.
        """
        shutil.copy2(DATA_FILES_DIR / "gke_1_32_containerd_1x_config.toml", wired["config_toml"])
        blob = textwrap.dedent("""\
            [plugins."io.containerd.grpc.v1.cri".registry.configs."registry.example.com".tls]
              ca_file = "/etc/containerd/certs.d/registry.example.com/my-ca.pem"
        """)
        script.CONTAINERD_CONFIG_TOML = blob

        mock_restart = self._run_main_once(
            script,
            "containerd github.com/containerd/containerd 1.7.29 abcdef",
        )

        import tomllib as _tomllib
        parsed = _tomllib.loads(wired["config_toml"].read_text())
        v1 = parsed["plugins"]["io.containerd.grpc.v1.cri"]["registry"]

        # The operator's blob landed as expected.
        tls = v1["configs"]["registry.example.com"]["tls"]
        assert tls["ca_file"].endswith("my-ca.pem")
        # Mirrors block from GKE's pristine config survives.
        assert "mirrors" in v1
        # config_path was NOT injected (1.x mirrors+config_path conflict).
        assert "config_path" not in v1

        # Containerd was restarted once (config.toml changed).
        mock_restart.assert_called_once()

        # The CA PEM was copied into certs.d/<registry>/ under its source name.
        assert (wired["certs_dir"] / "my-ca.pem").is_file()

        # No hosts.toml is written on 1.x (that's the 2.x strategy).
        assert not (wired["certs_dir"] / "hosts.toml").exists()

    def test_gke_132_containerd_1x_fails_without_customer_blob(self, script, wired):
        """If the operator hasn't set `containerdConfigToml`, the script must
        exit loudly — on 1.x we have no way to generate trust config ourselves."""
        shutil.copy2(DATA_FILES_DIR / "gke_1_32_containerd_1x_config.toml", wired["config_toml"])
        # Fixture already defaults CONTAINERD_CONFIG_TOML = "" — reaffirm:
        script.CONTAINERD_CONFIG_TOML = ""

        which_stub = "/usr/bin/nsenter"
        run_stub = _completed_process(
            "containerd github.com/containerd/containerd 1.7.29 abcdef"
        )

        with patch.object(script.shutil, "which", return_value=which_stub), \
             patch.object(script, "restart_containerd"), \
             patch("subprocess.run", return_value=run_stub), \
             patch.object(script.time, "sleep", side_effect=_StopLoop):
            # Missing blob → _apply_v1_customer_toml calls sys.exit(1).
            with pytest.raises(SystemExit) as excinfo:
                script.main()
            assert excinfo.value.code == 1

    def test_gke_133_containerd_2x_injects_v2_namespace_and_writes_hosts_toml(
        self, script, wired
    ):
        """Parallel assertion for containerd 2.x — different plugin namespace,
        everything else the same. Proves the two versions really do share a
        single code path post-unification."""
        shutil.copy2(DATA_FILES_DIR / "gke_1_33_containerd_2x_config.toml", wired["config_toml"])

        mock_restart = self._run_main_once(
            script,
            "containerd github.com/containerd/containerd/v2 2.0.7 abcdef",
        )

        import tomllib as _tomllib
        parsed = _tomllib.loads(wired["config_toml"].read_text())
        v2 = parsed["plugins"]["io.containerd.cri.v1.images"]["registry"]
        assert v2["config_path"] == "/etc/containerd/certs.d"

        mock_restart.assert_called_once()

        hosts_toml = (wired["certs_dir"] / "hosts.toml").read_text()
        assert "my-ca.pem" in hosts_toml
        assert (wired["certs_dir"] / "my-ca.pem").is_file()

    def test_config_path_already_set_does_not_restart(self, script, wired):
        """If config_path is already configured, startup must not restart
        containerd — steady-state cert rotation never restarts."""
        preconfigured = textwrap.dedent("""\
            [plugins."io.containerd.cri.v1.images".registry]
              config_path = "/etc/containerd/certs.d"
        """)
        wired["config_toml"].write_text(preconfigured)

        mock_restart = self._run_main_once(
            script,
            "containerd github.com/containerd/containerd/v2 2.0.7 abcdef",
        )

        mock_restart.assert_not_called()
        # hosts.toml still gets written on the first tick.
        assert (wired["certs_dir"] / "hosts.toml").is_file()
