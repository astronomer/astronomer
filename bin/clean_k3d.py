#!/usr/bin/env python3
"""Remove local k3d clusters and optional CP/DP host networking resources."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from k3d_setup_shared import (
    CP_DP_DNSMASQ_CONF_PATH,
    CP_DP_DNSMASQ_CONTAINER_NAME,
    CP_DP_LOCAL_DNS_PORT,
    CP_DP_PROXY_CONF_PATH,
    CP_DP_PROXY_CONTAINER_NAME,
    CommandError,
    _delete_k3d_cluster,
    _print,
    _run,
)

DEFAULT_CLUSTERS = ("cp01", "dp01", "astro037")
CP_DP_CLUSTER_NAME = re.compile(r"^(?:cp|dp)\d+$")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remove local Astronomer k3d resources.")
    parser.add_argument(
        "--cluster",
        action="append",
        dest="clusters",
        metavar="NAME",
        help="Cluster to delete; repeat for multiple clusters. Defaults to cp01, dp01, and astro037.",
    )
    parser.add_argument(
        "--base-domain",
        default="localtest.me",
        help="Base domain whose managed macOS resolver entry is removed. Default: %(default)s",
    )
    networking = parser.add_mutually_exclusive_group()
    networking.add_argument(
        "--cp-dp-networking",
        action="store_true",
        dest="cp_dp_networking",
        help="Also remove CP/DP DNS and SNI proxy resources for custom-named clusters.",
    )
    networking.add_argument(
        "--skip-cp-dp-networking",
        action="store_false",
        dest="cp_dp_networking",
        help="Keep the shared CP/DP DNS and SNI proxy resources.",
    )
    parser.set_defaults(cp_dp_networking=None)
    return parser.parse_args(argv)


def _selected_clusters(args: argparse.Namespace) -> tuple[str, ...]:
    return tuple(args.clusters) if args.clusters else DEFAULT_CLUSTERS


def _resolver_file_path(base_domain: str) -> Path:
    if not base_domain or base_domain in {".", ".."} or "/" in base_domain or "\\" in base_domain:
        raise ValueError(f"Invalid base domain for resolver path: {base_domain!r}")
    return Path("/etc/resolver") / base_domain


def _remove_managed_file(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _remove_resolver_file(base_domain: str) -> None:
    path = _resolver_file_path(base_domain)
    managed_contents = f"nameserver 127.0.0.1\nport {CP_DP_LOCAL_DNS_PORT}\n"
    try:
        contents = path.read_text()
    except FileNotFoundError:
        _print(f"  Resolver entry not found: {path}")
        return

    if contents != managed_contents:
        _print(f"  Preserving resolver entry with unrecognized contents: {path}")
        return

    _print(f"  Removing managed resolver entry: {path}")
    _run(["sudo", "rm", "-f", str(path)], check=True)


def _remove_container(name: str) -> None:
    inspect = _run(["docker", "inspect", name], check=False)
    if inspect.returncode != 0:
        stderr = (inspect.stderr or "").strip()
        if f"No such object: {name}" in stderr or f"No such container: {name}" in stderr:
            _print(f"  Container not found, skipping: {name}")
            return
        raise CommandError(f"Could not inspect container {name}: {stderr or 'docker inspect failed'}")
    _print(f"  Removing container: {name}")
    _run(["docker", "rm", "-f", name], check=True)


def _cleanup_cp_dp_networking(base_domain: str) -> list[str]:
    errors: list[str] = []
    containers = (
        (CP_DP_DNSMASQ_CONTAINER_NAME, CP_DP_DNSMASQ_CONF_PATH),
        (CP_DP_PROXY_CONTAINER_NAME, CP_DP_PROXY_CONF_PATH),
    )
    removed: dict[str, bool] = {}

    for name, config_path in containers:
        try:
            _remove_container(name)
            removed[name] = True
        except (CommandError, OSError, RuntimeError) as error:
            removed[name] = False
            errors.append(f"{name}: {error}")

        if removed[name]:
            try:
                _remove_managed_file(config_path)
            except OSError as error:
                errors.append(f"{config_path}: {error}")

    if removed.get(CP_DP_DNSMASQ_CONTAINER_NAME):
        try:
            _remove_resolver_file(base_domain)
        except (CommandError, OSError, RuntimeError, ValueError) as error:
            errors.append(f"resolver {base_domain}: {error}")

    return errors


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    clusters = _selected_clusters(args)
    errors: list[str] = []

    try:
        _run(["k3d", "cluster", "list"], check=True)
    except (CommandError, OSError, RuntimeError) as error:
        _print(f"Cannot query k3d clusters: {error}")
        return 1

    _print(f"Removing k3d clusters: {', '.join(clusters)}")
    for cluster in clusters:
        try:
            _delete_k3d_cluster(cluster)
        except (CommandError, OSError, RuntimeError) as error:
            errors.append(f"cluster {cluster}: {error}")

    has_cp_dp_cluster = any(CP_DP_CLUSTER_NAME.fullmatch(name) for name in clusters)
    remove_cp_dp_networking = args.cp_dp_networking if args.cp_dp_networking is not None else has_cp_dp_cluster
    if remove_cp_dp_networking:
        _print("Removing CP/DP local DNS and SNI proxy resources...")
        errors.extend(_cleanup_cp_dp_networking(args.base_domain))

    if errors:
        _print("\nCleanup completed with errors:")
        for error in errors:
            _print(f"  {error}")
        return 1

    _print("k3d cleanup complete. Shared registry caches, Docker network, certificates, and tools were preserved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
