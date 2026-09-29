from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "bin" / "clean_k3d.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("clean_k3d", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
clean_k3d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(clean_k3d)


def test_selected_clusters_defaults_and_custom_names() -> None:
    assert clean_k3d._selected_clusters(clean_k3d._parse_args([])) == ("cp01", "dp01", "astro037")
    args = clean_k3d._parse_args(["--cluster", "dev-cp", "--cluster", "dev-dp"])
    assert clean_k3d._selected_clusters(args) == ("dev-cp", "dev-dp")


def test_main_continues_after_cluster_delete_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    deleted: list[str] = []

    def delete_cluster(name: str) -> None:
        deleted.append(name)
        if name == "cp01":
            raise clean_k3d.CommandError("failed to delete")

    monkeypatch.setattr(clean_k3d, "_delete_k3d_cluster", delete_cluster)
    monkeypatch.setattr(clean_k3d, "_cleanup_cp_dp_networking", lambda _domain: [])
    monkeypatch.setattr(clean_k3d, "_run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0))

    assert clean_k3d.main([]) == 1
    assert deleted == ["cp01", "dp01", "astro037"]


def test_custom_non_cpdp_names_do_not_remove_shared_networking(monkeypatch: pytest.MonkeyPatch) -> None:
    deleted: list[str] = []
    networking: list[str] = []
    monkeypatch.setattr(clean_k3d, "_delete_k3d_cluster", deleted.append)
    monkeypatch.setattr(clean_k3d, "_cleanup_cp_dp_networking", networking.append)
    monkeypatch.setattr(clean_k3d, "_run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0))

    assert clean_k3d.main(["--cluster", "dev-astro"]) == 0
    assert deleted == ["dev-astro"]
    assert networking == []


def test_custom_cpdp_names_can_remove_shared_networking(monkeypatch: pytest.MonkeyPatch) -> None:
    networking: list[str] = []
    monkeypatch.setattr(clean_k3d, "_delete_k3d_cluster", lambda _name: None)

    def cleanup_networking(domain: str) -> list[str]:
        networking.append(domain)
        return []

    monkeypatch.setattr(clean_k3d, "_cleanup_cp_dp_networking", cleanup_networking)
    monkeypatch.setattr(clean_k3d, "_run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0))

    assert clean_k3d.main(["--cluster", "dev-cp", "--cp-dp-networking"]) == 0
    assert networking == ["localtest.me"]


def test_k3d_query_failure_aborts_before_deleting(monkeypatch: pytest.MonkeyPatch) -> None:
    deleted: list[str] = []

    def fail_query(*_args: object, **_kwargs: object) -> SimpleNamespace:
        raise clean_k3d.CommandError("Docker daemon unavailable")

    monkeypatch.setattr(clean_k3d, "_run", fail_query)
    monkeypatch.setattr(clean_k3d, "_delete_k3d_cluster", deleted.append)

    assert clean_k3d.main(["--cluster", "astro037"]) == 1
    assert deleted == []


def test_resolver_removed_only_when_contents_are_managed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    resolver = tmp_path / "localtest.me"
    resolver.write_text(f"nameserver 127.0.0.1\nport {clean_k3d.CP_DP_LOCAL_DNS_PORT}\n")
    commands: list[list[str]] = []
    monkeypatch.setattr(clean_k3d, "_resolver_file_path", lambda _domain: resolver)
    monkeypatch.setattr(clean_k3d, "_run", lambda command, **_kwargs: commands.append(command))

    clean_k3d._remove_resolver_file("localtest.me")
    assert commands == [["sudo", "rm", "-f", str(resolver)]]

    commands.clear()
    resolver.write_text("nameserver 8.8.8.8\n")
    clean_k3d._remove_resolver_file("localtest.me")
    assert commands == []


def test_network_cleanup_is_idempotent_when_resources_are_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def inspect_missing(command: list[str], **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stderr=f"Error: No such object: {command[2]}")

    monkeypatch.setattr(clean_k3d, "_run", inspect_missing)
    monkeypatch.setattr(clean_k3d, "_resolver_file_path", lambda _domain: tmp_path / "missing")
    monkeypatch.setattr(clean_k3d, "CP_DP_DNSMASQ_CONF_PATH", tmp_path / "dnsmasq.conf")
    monkeypatch.setattr(clean_k3d, "CP_DP_PROXY_CONF_PATH", tmp_path / "proxy.conf")

    assert clean_k3d._cleanup_cp_dp_networking("localtest.me") == []


def test_docker_inspection_error_preserves_configs_and_resolver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dns_config = tmp_path / "dnsmasq.conf"
    proxy_config = tmp_path / "proxy.conf"
    dns_config.write_text("managed dns config")
    proxy_config.write_text("managed proxy config")
    commands: list[list[str]] = []

    def docker_unavailable(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=1, stderr="Cannot connect to the Docker daemon")

    monkeypatch.setattr(clean_k3d, "_run", docker_unavailable)
    monkeypatch.setattr(clean_k3d, "CP_DP_DNSMASQ_CONF_PATH", dns_config)
    monkeypatch.setattr(clean_k3d, "CP_DP_PROXY_CONF_PATH", proxy_config)
    monkeypatch.setattr(clean_k3d, "_resolver_file_path", lambda _domain: tmp_path / "resolver")

    errors = clean_k3d._cleanup_cp_dp_networking("localtest.me")

    assert len(errors) == 2
    assert dns_config.read_text() == "managed dns config"
    assert proxy_config.read_text() == "managed proxy config"
    assert all(command[:2] == ["docker", "inspect"] for command in commands)


def test_invalid_domain_cannot_escape_resolver_directory() -> None:
    with pytest.raises(ValueError):
        clean_k3d._resolver_file_path("../hosts")