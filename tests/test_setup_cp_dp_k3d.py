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


def test_k3d_cluster_version_defaults_to_shared_version(setup_script):
    args = setup_script.parse_args([])

    assert args.k3d_cluster_version == setup_script.K3D_CLUSTER_VERSION


def test_k3d_cluster_version_can_be_overridden(setup_script):
    version = "v1.34.1-k3s1"

    args = setup_script.parse_args(["--k3d-cluster-version", version])

    assert args.k3d_cluster_version == version


def test_settings_keep_k3d_cluster_version(setup_script):
    version = "v1.34.1-k3s1"
    settings = setup_script.Settings(
        base_domain="localtest.me",
        namespace="astronomer",
        release_name="astronomer",
        docker_network="astronomer-net",
        cp_mode="unified",
        control_planes=(),
        data_planes=(),
        tls_secret_name="tls",  # noqa: S106
        mkcert_root_ca_secret_name="mkcert-ca",  # noqa: S106
        mkcert_root_ca_secret_key="ca.crt",  # noqa: S106
        helm_timeout="5m",
        helm_debug=False,
        dp_airflow_db="external",
        enable_operator=False,
        k3d_cluster_version=version,
    )

    assert settings.k3d_cluster_version == version
