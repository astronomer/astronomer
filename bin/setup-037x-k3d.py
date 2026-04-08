#!/usr/bin/env python3
"""
One-shot local 0.37.x Astronomer setup using a single k3d cluster.

This script automates spinning up a local 0.37.x Astronomer deployment:
- Generate TLS certs (mkcert) with the right SANs
- Create a k3d cluster on a Docker network
- Create namespace + secrets (TLS + mkcert root CA)
- Install the 0.37.x Astronomer chart from the remote Helm repo

The 0.37.x chart is a single-cluster deployment with no control/data plane
separation. It includes NATS + NATS Streaming (stan), Fluentd, Kibana, and
the Prometheus blackbox exporter.

Notes:
- No `/etc/hosts` changes are needed. `localtest.me` is a public wildcard DNS that resolves
  to 127.0.0.1, and port 443 is bound directly on the host. Adding a Docker-internal IP
  to /etc/hosts will break access on macOS (Docker Desktop / OrbStack).
- Safe to re-run: cluster/secrets/helm installs are done in an idempotent way.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

HELPER_DIR = Path.home() / ".local" / "share" / "astronomer-software"
HELPER_BIN_DIR = HELPER_DIR / "bin"
REGISTRY_CONFIG_DIR = HELPER_DIR / "registry-configs"
K3D_REGISTRY_CONFIG_PATH = HELPER_DIR / "k3d-registry.yaml"
REGISTRY_IMAGE = "registry:2"


# ---------------------------------------------------------------------------
# Local pull-through registry helpers
# (See bin/setup-local-registry.py for the standalone management script.)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RegistrySpec:
    name: str
    upstream: str
    host_port: int


_REGISTRY_SPECS: tuple[_RegistrySpec, ...] = (
    _RegistrySpec(name="astronomer-registry-proxy-quay", upstream="https://quay.io", host_port=15001),
    _RegistrySpec(name="astronomer-registry-proxy-docker", upstream="https://registry-1.docker.io", host_port=15002),
    _RegistrySpec(name="astronomer-registry-proxy-elastic", upstream="https://docker.elastic.co", host_port=15003),
    _RegistrySpec(name="astronomer-registry-proxy-k8s", upstream="https://registry.k8s.io", host_port=15004),
    _RegistrySpec(name="astronomer-registry-proxy-astrocrpublic", upstream="https://astrocrpublic.azurecr.io", host_port=15005),
)


def _registry_docker_config(spec: _RegistrySpec) -> str:
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


def _container_state(name: str) -> str | None:
    proc = _run(["docker", "inspect", name, "--format", "{{.State.Status}}"], check=False)
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def _container_networks(name: str) -> list[str]:
    proc = _run(["docker", "inspect", name, "--format", "{{json .NetworkSettings.Networks}}"], check=False)
    if proc.returncode != 0:
        return []
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        return list(json.loads(raw).keys())
    except json.JSONDecodeError:
        return []


def _ensure_registry(spec: _RegistrySpec, docker_network: str) -> None:
    config_path = REGISTRY_CONFIG_DIR / f"{spec.name}.yml"
    volume_name = f"{spec.name}-data"
    state = _container_state(spec.name)

    if state == "running":
        if docker_network not in _container_networks(spec.name):
            _run(["docker", "network", "connect", docker_network, spec.name])
        return

    if state is not None:
        _print(f"  Starting stopped registry container: {spec.name}")
        _run(["docker", "start", spec.name])
        if docker_network not in _container_networks(spec.name):
            _run(["docker", "network", "connect", docker_network, spec.name])
        return

    _print(f"  Creating registry proxy: {spec.name} -> {spec.upstream} (host port {spec.host_port})")
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


def _ensure_local_registries(docker_network: str) -> None:
    """Ensure all four pull-through registry proxy containers are running."""
    REGISTRY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for spec in _REGISTRY_SPECS:
        config_path = REGISTRY_CONFIG_DIR / f"{spec.name}.yml"
        config_path.write_text(_registry_docker_config(spec))
        _ensure_registry(spec, docker_network)


def _get_registry_config_path(docker_network: str) -> Path:
    """Write the k3d registry mirror config and return its path."""
    proxy_quay = "astronomer-registry-proxy-quay"
    proxy_docker = "astronomer-registry-proxy-docker"
    proxy_elastic = "astronomer-registry-proxy-elastic"
    proxy_k8s = "astronomer-registry-proxy-k8s"
    proxy_astrocrpublic = "astronomer-registry-proxy-astrocrpublic"

    content = f"""\
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
  "astrocrpublic.azurecr.io":
    endpoint:
      - "http://{proxy_astrocrpublic}:5000"
"""
    HELPER_DIR.mkdir(parents=True, exist_ok=True)
    K3D_REGISTRY_CONFIG_PATH.write_text(content)
    return K3D_REGISTRY_CONFIG_PATH


DEFAULT_CHART_VERSION = "0.37.7"
HELM_REPO_NAME = "astronomer-internal"
HELM_CHART = f"{HELM_REPO_NAME}/astronomer"
HELM_REPO_URL = "https://internal-helm.astronomer.io"


def _print(msg: str) -> None:
    print(msg, flush=True)


def _debug_enabled() -> bool:
    return os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"}


def _debug(msg: str) -> None:
    if _debug_enabled():
        _print(f"DEBUG: {msg}")


@dataclass(frozen=True)
class MilestoneHandle:
    idx: int


class Milestones:
    """Milestone logger with final summary table."""

    def __init__(self) -> None:
        self._idx = 0
        self._active: MilestoneHandle | None = None
        self._rows: list[dict[str, object]] = []

    def start(self, title: str) -> MilestoneHandle:
        self._idx += 1
        h = MilestoneHandle(idx=self._idx)
        self._active = h
        self._rows.append(
            {
                "idx": h.idx,
                "title": title,
                "status": "running",
                "started_at": time.monotonic(),
                "ended_at": None,
                "duration_s": None,
                "detail": "",
                "error": "",
            }
        )
        _print(f"\u23f3 [{h.idx:02d}] {title}")
        return h

    def done(self, h: MilestoneHandle, *, detail: str | None = None) -> None:
        row = self._row(h)
        row["status"] = "success"
        row["ended_at"] = time.monotonic()
        row["duration_s"] = float(row["ended_at"]) - float(row["started_at"])
        if detail:
            row["detail"] = detail
        if self._active == h:
            self._active = None

    def fail(self, h: MilestoneHandle, *, error: str) -> None:
        row = self._row(h)
        row["status"] = "failure"
        row["ended_at"] = time.monotonic()
        row["duration_s"] = float(row["ended_at"]) - float(row["started_at"])
        row["error"] = error
        if self._active == h:
            self._active = None

    def fail_active_if_any(self, *, error: str) -> None:
        if self._active is None:
            return
        self.fail(self._active, error=error)

    def skip(self, title: str, *, reason: str) -> None:
        self._idx += 1
        self._rows.append(
            {
                "idx": self._idx,
                "title": title,
                "status": "skipped",
                "started_at": None,
                "ended_at": None,
                "duration_s": 0.0,
                "detail": reason,
                "error": "",
            }
        )

    def print_summary_table(self) -> None:
        def _one_line(s: str) -> str:
            return " ".join(s.split())

        def _truncate(s: str, max_len: int) -> str:
            if len(s) <= max_len:
                return s
            return s[:max_len] if max_len <= 3 else f"{s[: max_len - 3]}..."

        rows: list[list[str]] = []
        for row in self._rows:
            idx = str(int(row["idx"]))
            title = _one_line(str(row["title"]))
            status = str(row["status"])
            duration_s = row.get("duration_s")
            detail = _one_line(str(row.get("detail") or ""))
            error = _one_line(str(row.get("error") or ""))

            status_cell = {
                "success": "\u2705 Success",
                "failure": "\u274c Failed",
                "skipped": "\u23ed\ufe0f Skipped",
                "running": "\u23f3 Running",
            }.get(status, status)

            duration_cell = "-"
            if isinstance(duration_s, (int, float)):
                duration_cell = f"{duration_s:.1f}s"

            details_cell = detail
            if error:
                details_cell = (f"{details_cell} " if details_cell else "") + error

            title = _truncate(title, 70)
            details_cell = _truncate(details_cell, 90)
            rows.append([idx, title, status_cell, duration_cell, details_cell])

        headers = ["#", "Milestone", "Status", "Duration", "Details"]
        widths = [len(h) for h in headers]
        for r in rows:
            for i, cell in enumerate(r):
                widths[i] = max(widths[i], len(cell))

        def _sep(char: str = "-") -> str:
            return "+".join([char * (w + 2) for w in widths]).join(["+", "+"])

        def _fmt_row(cells: list[str]) -> str:
            padded = [f" {cells[i].ljust(widths[i])} " for i in range(len(cells))]
            return "|" + "|".join(padded) + "|"

        _print("\nMilestones summary:\n")
        _print(_sep("-"))
        _print(_fmt_row(headers))
        _print(_sep("-"))
        for r in rows:
            _print(_fmt_row(r))
        _print(_sep("-"))

    def _row(self, h: MilestoneHandle) -> dict[str, object]:
        for row in reversed(self._rows):
            if int(row["idx"]) == h.idx:
                return row
        raise RuntimeError(f"Milestone handle not found: {h.idx}")


class CommandError(RuntimeError):
    """Raised when an external command fails."""


def _run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and optionally capture stdout/stderr."""
    _debug(f"run: {shlex.join(cmd)}")
    proc = subprocess.run(
        cmd,
        text=True,
        check=False,
        input=stdin,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        env=env,
    )
    if check and proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise CommandError(f"Command failed ({proc.returncode}): {shlex.join(cmd)}\n{stderr}")
    return proc


def _which(exe: str) -> str | None:
    proc = _run(["/usr/bin/env", "bash", "-lc", f"command -v {shlex.quote(exe)}"], check=False)
    path = (proc.stdout or "").strip()
    return path or None


def _require_executable(exe: str, *, hint: str) -> None:
    if _which(exe) is None:
        raise RuntimeError(f"Missing required executable `{exe}`. {hint}")


def _docker_network_exists(name: str) -> bool:
    proc = _run(["docker", "network", "inspect", name], check=False)
    return proc.returncode == 0


def _ensure_docker_network(name: str) -> None:
    if _docker_network_exists(name):
        return
    _print(f"Creating Docker network: {name}")
    _run(["docker", "network", "create", name], check=True)


def _k3d_cluster_exists(name: str) -> bool:
    proc = _run(["k3d", "cluster", "get", name], check=False)
    return proc.returncode == 0


def _delete_k3d_cluster(name: str) -> None:
    if not _k3d_cluster_exists(name):
        return
    _print(f"Deleting k3d cluster: {name}")
    _run(["k3d", "cluster", "delete", name], check=True)


def _mkcert_path() -> str:
    """Prefer our helper-installed mkcert if present, otherwise fall back to PATH."""
    helper = HELPER_BIN_DIR / "mkcert"
    if helper.exists():
        return str(helper)
    return "mkcert"


def _mkcert_caroot(mkcert_exe: str) -> Path:
    proc = _run([mkcert_exe, "-CAROOT"], check=True)
    caroot = Path(proc.stdout.strip())
    if not caroot.exists():
        raise RuntimeError(f"mkcert CAROOT does not exist: {caroot}")
    root_ca = caroot / "rootCA.pem"
    if not root_ca.exists():
        raise RuntimeError(f"mkcert rootCA.pem not found at: {root_ca}")
    return root_ca


@dataclass(frozen=True)
class Settings:
    base_domain: str
    namespace: str
    release_name: str
    docker_network: str
    cluster_name: str
    https_port: int
    http_port: int
    tls_secret_name: str
    mkcert_root_ca_secret_name: str
    mkcert_root_ca_secret_key: str
    chart_version: str
    helm_timeout: str
    helm_debug: bool
    agents: int = 0


def _ensure_tls_certs(settings: Settings) -> tuple[Path, Path, Path]:
    """Generate TLS certs with SANs for *.<baseDomain>.

    Returns:
        (cert_path, key_path, mkcert_root_ca_path)
    """
    mkcert_exe = _mkcert_path()
    _require_executable(
        mkcert_exe,
        hint="Install mkcert (or run `python3 bin/install-ci-tools.py` to install the repo-pinned version).",
    )

    cert_dir = Path.home() / ".local" / "share" / "astronomer-software" / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "astronomer-tls.pem"
    key_path = cert_dir / "astronomer-tls.key"

    root_ca = _mkcert_caroot(mkcert_exe)

    _print("Generating TLS certificates via mkcert")
    _run([mkcert_exe, "-install"], check=True)

    base = settings.base_domain
    sans = [base, f"*.{base}"]

    _run(
        [
            mkcert_exe,
            f"-cert-file={cert_path}",
            f"-key-file={key_path}",
            *sans,
        ],
        check=True,
    )

    root_ca_bytes = root_ca.read_bytes()
    cert_bytes = cert_path.read_bytes()
    if root_ca_bytes not in cert_bytes:
        cert_path.write_bytes(cert_bytes + b"\n" + root_ca_bytes)

    if not cert_path.exists() or not key_path.exists():
        raise RuntimeError(f"Failed to generate TLS certs at {cert_path} / {key_path}")

    return cert_path, key_path, root_ca


def _k3d_create_cluster(
    *,
    name: str,
    docker_network: str,
    ports: list[str],
    mkcert_root_ca: Path,
    agents: int = 1,
    registry_config: Path | None = None,
) -> None:
    """Create a k3d cluster with traefik disabled."""
    volume = f"{mkcert_root_ca}:/etc/ssl/certs/mkcert-rootCA.pem@server:*;agent:*"
    cmd = [
        "k3d",
        "cluster",
        "create",
        name,
        "--network",
        docker_network,
        "--agents",
        str(agents),
        "--k3s-arg",
        "--disable=traefik@server:0",
        "--volume",
        volume,
    ]
    if registry_config is not None:
        cmd.extend(["--registry-config", str(registry_config)])
    for p in ports:
        cmd.extend(["--port", p])

    _print(f"Creating k3d cluster: {name}")
    _run(cmd, check=True, capture=True)


def _kubectl_apply_yaml(context: str, yaml_text: str) -> None:
    _run(["kubectl", "--context", context, "apply", "-f", "-"], check=True, stdin=yaml_text)


def _kubectl_create_namespace(context: str, namespace: str) -> None:
    proc = _run(["kubectl", "--context", context, "create", "namespace", namespace], check=False)
    if proc.returncode == 0:
        return
    if "AlreadyExists" in (proc.stderr or ""):
        return
    raise CommandError(f"Failed to create namespace {namespace} (context={context}): {(proc.stderr or '').strip()}")


def _kubectl_apply_tls_secret(
    *,
    context: str,
    namespace: str,
    secret_name: str,
    cert_path: Path,
    key_path: Path,
) -> None:
    """Idempotently apply a TLS secret."""
    secret_yaml = _run(
        [
            "kubectl",
            "--context",
            context,
            "-n",
            namespace,
            "create",
            "secret",
            "tls",
            secret_name,
            f"--cert={cert_path}",
            f"--key={key_path}",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
        check=True,
    ).stdout
    _kubectl_apply_yaml(context, secret_yaml)


def _kubectl_apply_generic_secret_from_file(
    *,
    context: str,
    namespace: str,
    secret_name: str,
    key: str,
    file_path: Path,
) -> None:
    secret_yaml = _run(
        [
            "kubectl",
            "--context",
            context,
            "-n",
            namespace,
            "create",
            "secret",
            "generic",
            secret_name,
            f"--from-file={key}={file_path}",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
        check=True,
    ).stdout
    _kubectl_apply_yaml(context, secret_yaml)


def _ensure_helm_repo() -> None:
    """Ensure the Astronomer Helm repo is added and up-to-date."""
    proc = _run(["helm", "repo", "list", "-o", "json"], check=False)
    if HELM_REPO_NAME not in (proc.stdout or ""):
        _print(f"Adding Helm repo: {HELM_REPO_NAME} -> {HELM_REPO_URL}")
        _run(["helm", "repo", "add", HELM_REPO_NAME, HELM_REPO_URL], check=True)
    _run(["helm", "repo", "update", HELM_REPO_NAME], check=True)


def _values_yaml(settings: Settings) -> str:
    """Generate 0.37.x-schema values for a local single-cluster deployment."""
    return f"""\
global:
  baseDomain: {settings.base_domain}
  tlsSecret: {settings.tls_secret_name}
  postgresql:
    enabled: true
  privateCaCerts:
    - {settings.mkcert_root_ca_secret_name}
  rbacEnabled: true
  sccEnabled: false
  openshiftEnabled: false
  networkNSLabels: false
  namespaceFreeFormEntry: false
  taskUsageMetricsEnabled: false
  deployRollbackEnabled: false
  singleNamespace: false
  veleroEnabled: false
  nats:
    enabled: true
    replicas: 1
    jetStream:
      enabled: false
      tls: false
  stan:
    enabled: true
    replicas: 1
  networkPolicy:
    enabled: false
  defaultDenyNetworkPolicy: false
  dagOnlyDeployment:
    enabled: true
  loggingSidecar:
    enabled: false
  authSidecar:
    enabled: false

tags:
  platform: true
  monitoring: true
  logging: true
  stan: true

astronomer:
  astroUI:
    replicas: 1
    resources:
      requests:
        cpu: "50m"
        memory: "128Mi"
      limits:
        cpu: "250m"
        memory: "512Mi"
  houston:
    replicas: 1
    worker:
      replicas: 1
    config:
      emailConfirmation: false
      publicSignups: false
      auth:
        local:
          enabled: true
      deployments:
        configureDagDeployment: true
        hardDeleteDeployment: true
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
      limits:
        cpu: "250m"
        memory: "512Mi"
  commander:
    replicas: 1
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
      limits:
        cpu: "250m"
        memory: "512Mi"
  registry:
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
      limits:
        cpu: "250m"
        memory: "512Mi"

nginx:
  replicas: 1
  replicasDefaultBackend: 1
  resources:
    requests:
      cpu: "50m"
      memory: "128Mi"
    limits:
      cpu: "200m"
      memory: "256Mi"

grafana:
  resources:
    requests:
      cpu: "50m"
      memory: "128Mi"
    limits:
      cpu: "150m"
      memory: "256Mi"

prometheus:
  retention: 2d
  persistence:
    enabled: true
    size: "10Gi"
  resources:
    requests:
      cpu: "100m"
      memory: "512Mi"
    limits:
      cpu: "250m"
      memory: "1Gi"

nats:
  nats:
    resources:
      requests:
        cpu: "50m"
        memory: "30Mi"
      limits:
        cpu: "100m"
        memory: "64Mi"

stan:
  store:
    cluster:
      enabled: false
  stan:
    resources:
      requests:
        cpu: "50m"
        memory: "30Mi"
      limits:
        cpu: "100m"
        memory: "64Mi"
  init:
    resources:
      requests:
        cpu: "50m"
        memory: "30Mi"
      limits:
        cpu: "100m"
        memory: "64Mi"

elasticsearch:
  common:
    persistence:
      enabled: true
    env:
      NUMBER_OF_MASTERS: "1"
  master:
    replicas: 1
    heapMemory: 128m
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
    persistence:
      size: "10Gi"
  data:
    replicas: 1
    heapMemory: 256m
    resources:
      requests:
        cpu: "100m"
        memory: "512Mi"
    persistence:
      size: "20Gi"
  client:
    replicas: 1
    heapMemory: 128m
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
  images:
    es:
      repository: docker.elastic.co/elasticsearch/elasticsearch
      tag: "8.18.6"

kibana:
  resources:
    requests:
      cpu: "50m"
      memory: "256Mi"
    limits:
      cpu: "200m"
      memory: "512Mi"
  env:
    NODE_OPTIONS: "--max-old-space-size=384"

fluentd:
  resources:
    requests:
      cpu: "50m"
      memory: "128Mi"
    limits:
      cpu: "150m"
      memory: "256Mi"

kube-state:
  resources:
    requests:
      cpu: "50m"
      memory: "128Mi"
    limits:
      cpu: "150m"
      memory: "256Mi"

prometheus-blackbox-exporter:
  resources:
    requests:
      cpu: "50m"
      memory: "64Mi"
    limits:
      cpu: "100m"
      memory: "128Mi"

postgresql:
  postgresqlUsername: postgres
  postgresqlPassword: postgres
"""


def _docker_inspect_ip(container: str) -> str:
    proc = _run(
        ["docker", "inspect", container, "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
        check=True,
    )
    ip = proc.stdout.strip()
    if not ip:
        raise RuntimeError(f"Could not determine IP for container {container}")
    return ip


def _print_host_etc_hosts_instructions(settings: Settings) -> None:
    """Print DNS access instructions for the 0.37x single-cluster setup.

    Unlike the CP/DP setup, NO /etc/hosts entry is needed here.

    Reason: this cluster binds port 443 directly to 0.0.0.0:443 on the host, and
    `localtest.me` is a public wildcard DNS that resolves *.localtest.me -> 127.0.0.1.
    So https://app.localtest.me reaches the cluster via localhost:443 with no host
    DNS overrides required.

    Adding a /etc/hosts entry pointing to the Docker-internal container IP will
    *break* access on macOS (Docker Desktop / OrbStack) because that IP is only
    reachable inside the Docker network, not from the host.
    """
    base = settings.base_domain

    _print(
        f"\n\u2139\ufe0f  No /etc/hosts changes needed for this setup.\n"
        f"   `{base}` is a public wildcard DNS that resolves to 127.0.0.1,\n"
        f"   and port {settings.https_port} is bound directly on localhost.\n"
        f"\n"
        f"   If you previously added a Docker IP to /etc/hosts for this domain,\n"
        f"   remove it — it will cause connection timeouts on macOS:\n"
        f"\n"
        f"     sudo sed -i '' '/{base}/d' /etc/hosts\n"
    )


def _validate_prereqs() -> None:
    _require_executable("docker", hint="Install Docker Desktop/OrbStack and ensure `docker` works.")
    _require_executable("k3d", hint="Install k3d (e.g. `brew install k3d` on macOS).")
    _require_executable("kubectl", hint="Install kubectl and ensure it is in PATH.")
    _require_executable("helm", hint="Install helm and ensure it is in PATH.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Spin up a local Astronomer 0.37.x deployment using a single k3d cluster.",
    )
    parser.add_argument("--base-domain", default="localtest.me")
    parser.add_argument("--namespace", default="astronomer")
    parser.add_argument("--release-name", default="astronomer")
    parser.add_argument("--docker-network", default="astronomer-net")
    parser.add_argument("--cluster-name", default="astro037")
    parser.add_argument("--https-port", type=int, default=443, help="HTTPS port. Default: '%(default)s'")
    parser.add_argument("--http-port", type=int, default=80, help="HTTP port. Default: '%(default)s'")
    parser.add_argument("--tls-secret-name", default="astronomer-tls")
    parser.add_argument("--mkcert-root-ca-secret-name", default="mkcert-root-ca")
    parser.add_argument("--mkcert-root-ca-secret-key", default="cert.pem")
    parser.add_argument(
        "--chart-version",
        default=DEFAULT_CHART_VERSION,
        help="Astronomer chart version to install. Default: '%(default)s'",
    )
    parser.add_argument("--helm-timeout", default=os.environ.get("HELM_TIMEOUT", "60m"))
    parser.add_argument("--helm-debug", action="store_true")
    parser.add_argument("--recreate-cluster", action="store_true", help="Delete and recreate k3d cluster if it exists")
    parser.add_argument(
        "--agents",
        type=int,
        default=0,
        help="Number of k3d agent (worker) nodes to create alongside the server node. Default: %(default)s. Prefer allocating more CPU/memory in Docker Desktop over adding agents.",
    )
    parser.add_argument(
        "--no-local-registry",
        action="store_true",
        help=(
            "Skip the local pull-through registry proxy setup. "
            "Images will be pulled directly from remote registries (may be rate-limited). "
            "Use bin/setup-local-registry.py to manage the registry containers separately."
        ),
    )

    parser.add_argument("--skip-certs", action="store_true")
    parser.add_argument("--skip-cluster", action="store_true")
    parser.add_argument("--skip-secrets", action="store_true")
    parser.add_argument("--skip-helm", action="store_true")

    parser.add_argument(
        "--values-dir",
        default="",
        help="Directory to write values.yaml. Defaults to a temp directory.",
    )
    parser.add_argument(
        "--helm-values",
        action="append",
        default=[],
        dest="helm_values",
        metavar="FILE",
        help="Extra Helm values file (can be repeated).",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ms = Milestones()

    settings = Settings(
        base_domain=args.base_domain,
        namespace=args.namespace,
        release_name=args.release_name,
        docker_network=args.docker_network,
        cluster_name=args.cluster_name,
        https_port=args.https_port,
        http_port=args.http_port,
        tls_secret_name=args.tls_secret_name,
        mkcert_root_ca_secret_name=args.mkcert_root_ca_secret_name,
        mkcert_root_ca_secret_key=args.mkcert_root_ca_secret_key,
        chart_version=args.chart_version,
        helm_timeout=args.helm_timeout,
        helm_debug=bool(args.helm_debug),
        agents=args.agents,
    )

    context = f"k3d-{settings.cluster_name}"

    try:
        h = ms.start("Validate prerequisites (docker/k3d/kubectl/helm)")
        _validate_prereqs()
        ms.done(h)

        h = ms.start(f"Ensure Docker network `{settings.docker_network}` exists")
        _ensure_docker_network(settings.docker_network)
        ms.done(h)

        registry_config: Path | None = None
        if not args.no_local_registry:
            h = ms.start("Ensure local pull-through registry proxy containers are running")
            _ensure_local_registries(settings.docker_network)
            registry_config = _get_registry_config_path(settings.docker_network)
            ms.done(h, detail=f"config={registry_config}")
        else:
            ms.skip("Local registry proxy setup", reason="--no-local-registry set")

        cert_path: Path | None = None
        key_path: Path | None = None
        mkcert_root_ca: Path | None = None
        if not args.skip_certs:
            h = ms.start("Generate TLS certs (mkcert)")
            cert_path, key_path, mkcert_root_ca = _ensure_tls_certs(settings)
            ms.done(h, detail=f"cert={cert_path} key={key_path}")
        else:
            ms.skip("Generate TLS certs (mkcert)", reason="--skip-certs set")
            mkcert_root_ca = _mkcert_caroot(_mkcert_path())
            cert_dir = Path.home() / ".local" / "share" / "astronomer-software" / "certs"
            cert_path = cert_dir / "astronomer-tls.pem"
            key_path = cert_dir / "astronomer-tls.key"

        if mkcert_root_ca is None:
            raise RuntimeError("mkcert root CA path not available")

        if not args.skip_cluster:
            h = ms.start(f"Ensure k3d cluster `{settings.cluster_name}` exists")
            if args.recreate_cluster:
                _delete_k3d_cluster(settings.cluster_name)

            if not _k3d_cluster_exists(settings.cluster_name):
                _k3d_create_cluster(
                    name=settings.cluster_name,
                    docker_network=settings.docker_network,
                    ports=[
                        f"{settings.https_port}:443@loadbalancer",
                        f"{settings.http_port}:80@loadbalancer",
                    ],
                    mkcert_root_ca=mkcert_root_ca,
                    agents=settings.agents,
                    registry_config=registry_config,
                )
            else:
                _debug(f"Cluster already exists, skipping: {settings.cluster_name}")
            ms.done(h)
        else:
            ms.skip(f"Ensure k3d cluster `{settings.cluster_name}` exists", reason="--skip-cluster set")

        if not args.skip_secrets:
            h = ms.start(f"Apply namespace + secrets (ns={settings.namespace})")
            if cert_path is None or key_path is None:
                raise RuntimeError("TLS cert/key paths not available; cannot create secrets")

            _kubectl_create_namespace(context, settings.namespace)
            _kubectl_apply_tls_secret(
                context=context,
                namespace=settings.namespace,
                secret_name=settings.tls_secret_name,
                cert_path=cert_path,
                key_path=key_path,
            )
            _kubectl_apply_generic_secret_from_file(
                context=context,
                namespace=settings.namespace,
                secret_name=settings.mkcert_root_ca_secret_name,
                key=settings.mkcert_root_ca_secret_key,
                file_path=mkcert_root_ca,
            )
            ms.done(h, detail=f"tlsSecret={settings.tls_secret_name}")
        else:
            ms.skip("Apply namespace + secrets", reason="--skip-secrets set")

        if not args.skip_helm:
            h = ms.start(f"Ensure Helm repo `{HELM_REPO_NAME}` is up-to-date")
            _ensure_helm_repo()
            ms.done(h)

            h = ms.start("Write Helm values file")
            values_dir: Path
            if args.values_dir:
                values_dir = Path(args.values_dir)
                values_dir.mkdir(parents=True, exist_ok=True)
            else:
                values_dir = Path(tempfile.mkdtemp(prefix="astro-037x-k3d-"))

            values_file = values_dir / "values.yaml"
            values_file.write_text(_values_yaml(settings))
            ms.done(h, detail=f"file={values_file}")

            h = ms.start(f"Helm install/upgrade Astronomer {settings.chart_version} (context={context})")
            cmd = [
                "helm",
                "upgrade",
                "--install",
                settings.release_name,
                HELM_CHART,
                "--version",
                settings.chart_version,
                "--namespace",
                settings.namespace,
                "--kube-context",
                context,
                "--values",
                str(values_file),
                "--timeout",
                settings.helm_timeout,
                "--wait",
            ]
            for extra in args.helm_values:
                cmd.extend(["--values", extra])
            if settings.helm_debug:
                cmd.append("--debug")
            _print(f"Installing Astronomer {settings.chart_version} ...")
            _run(cmd, check=True, capture=False)
            ms.done(h)
        else:
            ms.skip("Helm install", reason="--skip-helm set")

        ms.print_summary_table()
        _print_host_etc_hosts_instructions(settings)
        port_suffix = "" if settings.https_port == 443 else f":{settings.https_port}"
        _print(f"\n\u2705 Astronomer {settings.chart_version} is running on k3d cluster `{settings.cluster_name}`.")
        _print(f"   kubectl context: {context}")
        _print(f"   Astro UI: https://app.{settings.base_domain}{port_suffix}")
        _print(f"   Houston:  https://houston.{settings.base_domain}{port_suffix}/v1")
        _print(f"   Grafana:  https://grafana.{settings.base_domain}{port_suffix}")
        _print(f"   Kibana:   https://kibana.{settings.base_domain}{port_suffix}")
        return 0
    except Exception as e:  # noqa: BLE001
        ms.fail_active_if_any(error=str(e))
        ms.print_summary_table()
        _print(f"\n\u274c Failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
