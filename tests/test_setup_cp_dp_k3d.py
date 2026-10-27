import importlib.util
import sys
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parents[1] / "bin"
SCRIPT_PATH = BIN_DIR / "setup-cp-dp-k3d.py"


@pytest.fixture
def setup_script(monkeypatch):
    monkeypatch.syspath_prepend(str(BIN_DIR))
    spec = importlib.util.spec_from_file_location("setup_cp_dp_k3d", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def _settings_kwargs():
    return {
        "base_domain": "localtest.me",
        "namespace": "astronomer",
        "release_name": "astronomer",
        "docker_network": "astronomer-net",
        "cp_mode": "unified",
        "control_planes": (),
        "data_planes": (),
        "tls_secret_name": "tls",
        "mkcert_root_ca_secret_name": "mkcert-ca",
        "mkcert_root_ca_secret_key": "ca.crt",
        "helm_timeout": "5m",
        "helm_debug": False,
        "dp_airflow_db": "external",
        "enable_operator": False,
    }


def _helm_cmd(setup_script, monkeypatch, tmp_path, **kwargs):
    """Run _helm_upgrade_install with _run stubbed out and return the helm command it built."""
    captured = []
    monkeypatch.setattr(setup_script, "_run", lambda cmd, **_: captured.append(cmd))
    setup_script._helm_upgrade_install(
        context="k3d-cp01",
        chart_dir=tmp_path,
        release_name="astronomer",
        namespace="astronomer",
        values_file=tmp_path / "values.yaml",
        extra_values_files=[],
        timeout="5m",
        debug=False,
        **kwargs,
    )
    assert len(captured) == 1
    return captured[0]


@pytest.mark.parametrize("value", [True, False])
def test_settings_force_incompatible_kubernetes_version_explicit(setup_script, value):
    settings = setup_script.Settings(**_settings_kwargs(), force_incompatible_kubernetes_version=value)

    assert settings.force_incompatible_kubernetes_version is value


def test_settings_force_incompatible_kubernetes_version_defaults_to_true(setup_script):
    settings = setup_script.Settings(**_settings_kwargs())

    assert settings.force_incompatible_kubernetes_version is True


def test_parse_args_force_incompatible_kubernetes_version_defaults_to_true(setup_script):
    assert setup_script.parse_args([]).force_incompatible_kubernetes_version is True


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("--force-incompatible-kubernetes-version", True),
        ("--no-force-incompatible-kubernetes-version", False),
    ],
)
def test_parse_args_force_incompatible_kubernetes_version_flags(setup_script, flag, expected):
    assert setup_script.parse_args([flag]).force_incompatible_kubernetes_version is expected


def test_helm_upgrade_install_forces_incompatible_kubernetes_version_by_default(setup_script, monkeypatch, tmp_path):
    cmd = _helm_cmd(setup_script, monkeypatch, tmp_path)

    assert "forceIncompatibleKubernetes=true" in cmd
    assert cmd[cmd.index("forceIncompatibleKubernetes=true") - 1] == "--set"


def test_helm_upgrade_install_omits_force_incompatible_kubernetes_version_when_disabled(setup_script, monkeypatch, tmp_path):
    cmd = _helm_cmd(setup_script, monkeypatch, tmp_path, force_incompatible_kubernetes_version=False)

    assert not any("forceIncompatibleKubernetes" in arg for arg in cmd)
