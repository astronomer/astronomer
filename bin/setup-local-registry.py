#!/usr/bin/env python3
"""
Manage persistent local pull-through caching registry containers for k3d development.

Runs four Docker Registry v2 containers (one per upstream) on the shared Docker network.
The containers survive k3d cluster destroy/recreate because they live outside any cluster.

Registries managed:
  astronomer-registry-proxy-quay     -> quay.io          (host port 15001)
  astronomer-registry-proxy-docker   -> docker.io         (host port 15002)
  astronomer-registry-proxy-elastic  -> docker.elastic.co (host port 15003)
  astronomer-registry-proxy-k8s     -> registry.k8s.io   (host port 15004)

Usage:
  python3 bin/setup-local-registry.py                    # ensure all registries are up
  python3 bin/setup-local-registry.py --status           # print container status table
  python3 bin/setup-local-registry.py --destroy          # stop + remove containers (keeps volumes)
  python3 bin/setup-local-registry.py --destroy --purge  # also remove cache volumes
  python3 bin/setup-local-registry.py --docker-network <name>
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HELPER_DIR = Path.home() / ".local" / "share" / "astronomer-software"
REGISTRY_CONFIG_DIR = HELPER_DIR / "registry-configs"
K3D_REGISTRY_CONFIG_PATH = HELPER_DIR / "k3d-registry.yaml"

REGISTRY_IMAGE = "registry:2"

DEFAULT_DOCKER_NETWORK = "astronomer-net"


@dataclass(frozen=True)
class RegistrySpec:
    name: str  # Docker container name
    upstream: str  # Full upstream URL (https://...)
    host_port: int  # Port exposed on the host for direct docker pull


REGISTRY_SPECS: tuple[RegistrySpec, ...] = (
    RegistrySpec(
        name="astronomer-registry-proxy-quay",
        upstream="https://quay.io",
        host_port=15001,
    ),
    RegistrySpec(
        name="astronomer-registry-proxy-docker",
        upstream="https://registry-1.docker.io",
        host_port=15002,
    ),
    RegistrySpec(
        name="astronomer-registry-proxy-elastic",
        upstream="https://docker.elastic.co",
        host_port=15003,
    ),
    RegistrySpec(
        name="astronomer-registry-proxy-k8s",
        upstream="https://registry.k8s.io",
        host_port=15004,
    ),
)


def _print(msg: str) -> None:
    print(msg, flush=True)


def _debug_enabled() -> bool:
    return os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"}


def _debug(msg: str) -> None:
    if _debug_enabled():
        _print(f"DEBUG: {msg}")


def _run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    _debug(f"run: {shlex.join(cmd)}")
    proc = subprocess.run(
        cmd,
        text=True,
        check=False,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(f"Command failed ({proc.returncode}): {shlex.join(cmd)}\n{stderr}")
    return proc


def _docker_network_exists(name: str) -> bool:
    return _run(["docker", "network", "inspect", name], check=False).returncode == 0


def _ensure_docker_network(name: str) -> None:
    if _docker_network_exists(name):
        return
    _print(f"Creating Docker network: {name}")
    _run(["docker", "network", "create", name])


def _container_state(name: str) -> str | None:
    """Return container state string ('running', 'exited', …) or None if not found."""
    proc = _run(
        ["docker", "inspect", name, "--format", "{{.State.Status}}"],
        check=False,
    )
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def _container_networks(name: str) -> list[str]:
    """Return list of network names the container is attached to."""
    proc = _run(
        ["docker", "inspect", name, "--format", "{{json .NetworkSettings.Networks}}"],
        check=False,
    )
    if proc.returncode != 0:
        return []
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        nets = json.loads(raw)
        return list(nets.keys())
    except json.JSONDecodeError:
        return []


def _registry_docker_config(spec: RegistrySpec) -> str:
    """Generate registry:2 YAML config for a pull-through proxy."""
    return f"""\
version: 0.1
log:
  level: warn
storage:
  filesystem:
    rootdirectory: /var/lib/registry
  delete:
    enabled: true
http:
  addr: :5000
proxy:
  remoteurl: {spec.upstream}
"""


def _write_registry_configs() -> None:
    """Write per-registry config files to the host filesystem."""
    REGISTRY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for spec in REGISTRY_SPECS:
        config_path = REGISTRY_CONFIG_DIR / f"{spec.name}.yml"
        config_path.write_text(_registry_docker_config(spec))
        _debug(f"Wrote registry config: {config_path}")


def _ensure_registry(spec: RegistrySpec, docker_network: str) -> None:
    """Idempotently ensure a single registry proxy container is running."""
    config_path = REGISTRY_CONFIG_DIR / f"{spec.name}.yml"
    volume_name = f"{spec.name}-data"

    state = _container_state(spec.name)

    if state == "running":
        # Make sure it's on the right network (could be missing after network recreation).
        if docker_network not in _container_networks(spec.name):
            _print(f"  Attaching {spec.name} to network {docker_network}")
            _run(["docker", "network", "connect", docker_network, spec.name])
        _debug(f"Registry already running: {spec.name}")
        return

    if state is not None:
        # Container exists but is stopped — start it.
        _print(f"  Starting stopped registry container: {spec.name}")
        _run(["docker", "start", spec.name])
        if docker_network not in _container_networks(spec.name):
            _run(["docker", "network", "connect", docker_network, spec.name])
        return

    # Container does not exist — create it.
    _print(f"  Creating registry proxy container: {spec.name} ({spec.upstream}) on port {spec.host_port}")
    _run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            spec.name,
            "--network",
            docker_network,
            "--restart",
            "always",
            "-p",
            f"{spec.host_port}:5000",
            "-v",
            f"{volume_name}:/var/lib/registry",
            "-v",
            f"{config_path}:/etc/docker/registry/config.yml:ro",
            REGISTRY_IMAGE,
        ]
    )


def _ensure_local_registries(docker_network: str = DEFAULT_DOCKER_NETWORK) -> None:
    """Ensure all four registry proxy containers are running on the given Docker network.

    This is the primary entry point called by the k3d setup scripts before cluster creation.
    It is safe to call repeatedly (idempotent).
    """
    _ensure_docker_network(docker_network)
    _write_registry_configs()
    for spec in REGISTRY_SPECS:
        _ensure_registry(spec, docker_network)


def _k3d_registry_config_yaml(docker_network: str = DEFAULT_DOCKER_NETWORK) -> str:
    """Generate the k3d --registry-config YAML content.

    Maps each upstream registry hostname to the local pull-through proxy.
    The file is passed to `k3d cluster create --registry-config <path>` so that
    containerd inside each k3d node uses the local cache for all image pulls.

    Note: `docker.io` and `index.docker.io` are two aliases Docker clients use for
    Docker Hub; both are listed so pulls from either path are intercepted.
    """
    proxy_quay = "astronomer-registry-proxy-quay"
    proxy_docker = "astronomer-registry-proxy-docker"
    proxy_elastic = "astronomer-registry-proxy-elastic"
    proxy_k8s = "astronomer-registry-proxy-k8s"

    return f"""\
mirrors:
  "quay.io":
    endpoint:
      - "http://{proxy_quay}:5000"
  "docker.io":
    endpoint:
      - "http://{proxy_docker}:5000"
  "index.docker.io":
    endpoint:
      - "http://{proxy_docker}:5000"
  "docker.elastic.co":
    endpoint:
      - "http://{proxy_elastic}:5000"
  "registry.k8s.io":
    endpoint:
      - "http://{proxy_k8s}:5000"
"""


def _write_k3d_registry_config(docker_network: str = DEFAULT_DOCKER_NETWORK) -> Path:
    """Write the k3d registry config YAML to a stable path and return it."""
    HELPER_DIR.mkdir(parents=True, exist_ok=True)
    K3D_REGISTRY_CONFIG_PATH.write_text(_k3d_registry_config_yaml(docker_network))
    return K3D_REGISTRY_CONFIG_PATH


def get_registry_config_path(docker_network: str = DEFAULT_DOCKER_NETWORK) -> Path:
    """Return the k3d registry config path, writing it first if needed.

    Called by setup-037x-k3d.py and setup-cp-dp-k3d.py before cluster creation.
    """
    return _write_k3d_registry_config(docker_network)


# ---------------------------------------------------------------------------
# Status + destroy helpers (used by the standalone CLI only)
# ---------------------------------------------------------------------------


def _status_table() -> None:
    """Print a human-readable status table of all registry containers."""
    rows = []
    for spec in REGISTRY_SPECS:
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
    for spec in REGISTRY_SPECS:
        state = _container_state(spec.name)
        if state is None:
            _print(f"  {spec.name}: not found, skipping")
            continue
        _print(f"  Removing container: {spec.name}")
        _run(["docker", "rm", "-f", spec.name])

    if purge_volumes:
        for spec in REGISTRY_SPECS:
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
    _ensure_local_registries(args.docker_network)
    config_path = get_registry_config_path(args.docker_network)
    _print(f"\nk3d registry config written to: {config_path}")
    _print("\nRegistry proxies are ready. Pass the following flag to k3d cluster create:")
    _print(f"  --registry-config {config_path}")
    _print("")
    _print("Direct pull access from host (after docker login if needed):")
    for spec in REGISTRY_SPECS:
        _print(f"  {spec.upstream.replace('https://', '')}  ->  localhost:{spec.host_port}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
