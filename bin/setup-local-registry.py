#!/usr/bin/env python3
"""
Manage persistent local pull-through caching registry containers for k3d development.

Runs one Docker Registry v2 container per upstream on the shared Docker network. The containers
survive k3d cluster destroy/recreate because they live outside any cluster.

The container set, their config, and the ensure logic live in `k3d_setup_shared.py`, so the k3d
setup scripts and this CLI always manage exactly the same containers. This script adds only what
is specific to managing them by hand: status and destroy.

Registries managed:
  astronomer-registry-proxy-quay          -> quay.io                    (host port 15001)
  astronomer-registry-proxy-docker        -> docker.io                  (host port 15002)
  astronomer-registry-proxy-elastic       -> docker.elastic.co          (host port 15003)
  astronomer-registry-proxy-k8s           -> registry.k8s.io            (host port 15004)
  astronomer-registry-proxy-astrocrpublic -> astrocrpublic.azurecr.io   (host port 15005)

Usage:
  python3 bin/setup-local-registry.py                    # ensure all registries are up
  python3 bin/setup-local-registry.py --status           # print container status table
  python3 bin/setup-local-registry.py --destroy          # stop + remove containers (keeps volumes)
  python3 bin/setup-local-registry.py --destroy --purge  # also remove cache volumes
  python3 bin/setup-local-registry.py --docker-network <name>
"""

from __future__ import annotations

import argparse
import sys

from k3d_setup_shared import (
    _REGISTRY_SPECS,
    DEFAULT_DOCKER_NETWORK,
    _container_networks,
    _container_state,
    _ensure_docker_network,
    _ensure_local_registries,
    _get_registry_config_path,
    _print,
    _run,
)

# ---------------------------------------------------------------------------
# Status + destroy helpers (used by this CLI only)
# ---------------------------------------------------------------------------


def _status_table() -> None:
    """Print a human-readable status table of all registry containers."""
    rows = []
    for spec in _REGISTRY_SPECS:
        state = _container_state(spec.name) or "missing"
        nets = _container_networks(spec.name)
        rows.append((spec.name, spec.upstream, str(spec.host_port), state, ", ".join(nets) or "-"))

    headers = ["Container", "Upstream", "Host Port", "State", "Networks"]
    widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def _row(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"

    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    _print("\nLocal registry proxy status:\n")
    _print(sep)
    _print(_row(headers))
    _print(sep)
    for r in rows:
        _print(_row(list(r)))
    _print(sep)
    _print("")


def _destroy(*, purge_volumes: bool = False) -> None:
    """Stop and remove all registry containers. Optionally purge cache volumes."""
    for spec in _REGISTRY_SPECS:
        state = _container_state(spec.name)
        if state is None:
            _print(f"  {spec.name}: not found, skipping")
            continue
        _print(f"  Removing container: {spec.name}")
        _run(["docker", "rm", "-f", spec.name])

    if purge_volumes:
        for spec in _REGISTRY_SPECS:
            volume_name = f"{spec.name}-data"
            proc = _run(["docker", "volume", "inspect", volume_name], check=False)
            if proc.returncode != 0:
                _print(f"  Volume {volume_name}: not found, skipping")
                continue
            _print(f"  Removing volume: {volume_name}")
            _run(["docker", "volume", "rm", volume_name])


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage local pull-through registry proxy containers for k3d development.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--docker-network",
        default=DEFAULT_DOCKER_NETWORK,
        help="Docker network to attach registry containers to. Default: '%(default)s'",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print container status table and exit.",
    )
    parser.add_argument(
        "--destroy",
        action="store_true",
        help="Stop and remove registry containers (cache volumes are preserved).",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="When used with --destroy, also remove cache volumes (clears all cached images).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.status:
        _status_table()
        return 0

    if args.destroy:
        _print("Destroying local registry proxy containers...")
        _destroy(purge_volumes=args.purge)
        if args.purge:
            _print("Cache volumes removed. All cached images have been purged.")
        else:
            _print("Containers removed. Cache volumes retained (re-run without --destroy to restart).")
        return 0

    _print("Ensuring local registry proxy containers are running...")
    _ensure_docker_network(args.docker_network)
    _ensure_local_registries(args.docker_network)
    config_path = _get_registry_config_path()
    _print(f"\nk3d registry config written to: {config_path}")
    _print("\nRegistry proxies are ready. Pass the following flag to k3d cluster create:")
    _print(f"  --registry-config {config_path}")
    _print("")
    _print("Direct pull access from host (after docker login if needed):")
    for spec in _REGISTRY_SPECS:
        _print(f"  {spec.upstream.replace('https://', '')}  ->  localhost:{spec.host_port}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
