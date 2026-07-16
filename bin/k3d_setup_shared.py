#!/usr/bin/env python3
"""
Shared helpers for the local k3d setup scripts (setup-cp-dp-k3d.py, setup-037x-k3d.py).

Not a standalone entry point — imported directly (both scripts live in this same `bin/`
directory, which Python puts on `sys.path` automatically when the script is run, matching the
existing `helm_chart_values_migration_shared.py` / `certs.py` sibling-import pattern in this repo).

Covers the boilerplate that has no reason to differ between scripts: process/logging plumbing,
Docker/k3d cluster management, the local pull-through registry proxy, mkcert TLS generation,
kubectl secret/namespace helpers, and cert-manager install. Anything that encodes a script's own
install topology (Helm values generation, SAN lists, CLI flags, main()) stays in that script.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

HELPER_DIR = Path.home() / ".local" / "share" / "astronomer-software"
HELPER_BIN_DIR = HELPER_DIR / "bin"
REGISTRY_CONFIG_DIR = HELPER_DIR / "registry-configs"
K3D_REGISTRY_CONFIG_PATH = HELPER_DIR / "k3d-registry.yaml"
REGISTRY_IMAGE = "registry:2"

HELM_REPO_NAME = "astronomer-internal"
HELM_CHART = f"{HELM_REPO_NAME}/astronomer"
HELM_REPO_URL = "https://internal-helm.astronomer.io"

CERT_MANAGER_VERSION = "v1.19.4"
CERT_MANAGER_MANIFEST_URL = f"https://github.com/jetstack/cert-manager/releases/download/{CERT_MANAGER_VERSION}/cert-manager.yaml"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _print(msg: str) -> None:
    print(msg, flush=True)


def _debug_enabled() -> bool:
    return os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"}


def _debug(msg: str) -> None:
    if _debug_enabled():
        _print(f"DEBUG: {msg}")


# ---------------------------------------------------------------------------
# Milestone tracker: minimal live output + a final ✅/❌ summary table.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MilestoneHandle:
    idx: int


class Milestones:
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
        _print(f"⏳ [{h.idx:02d}] {title}")
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
                "success": "✅ Success",
                "failure": "❌ Failed",
                "skipped": "⏭️ Skipped",
                "running": "⏳ Running",
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


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------


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


def _validate_prereqs() -> None:
    _require_executable("docker", hint="Install Docker Desktop/OrbStack and ensure `docker` works.")
    _require_executable("k3d", hint="Install k3d (e.g. `brew install k3d` on macOS).")
    _require_executable("kubectl", hint="Install kubectl and ensure it is in PATH.")
    _require_executable("helm", hint="Install helm and ensure it is in PATH.")


def _ensure_helm_repo(repo_name: str = HELM_REPO_NAME, repo_url: str = HELM_REPO_URL) -> None:
    """Ensure the given Helm repo is added and up-to-date."""
    proc = _run(["helm", "repo", "list", "-o", "json"], check=False)
    if repo_name not in (proc.stdout or ""):
        _print(f"Adding Helm repo: {repo_name} -> {repo_url}")
        _run(["helm", "repo", "add", repo_name, repo_url], check=True)
    _run(["helm", "repo", "update", repo_name], check=True)


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
    """Ensure all pull-through registry proxy containers are running on `docker_network`."""
    REGISTRY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for spec in _REGISTRY_SPECS:
        config_path = REGISTRY_CONFIG_DIR / f"{spec.name}.yml"
        config_path.write_text(_registry_docker_config(spec))
        _ensure_registry(spec, docker_network)


def _get_registry_config_path(_docker_network: str = "") -> Path:
    """Write the k3d registry mirror config and return its path."""
    content = """\
mirrors:
  "quay.io":
    endpoint:
      - "http://astronomer-registry-proxy-quay:5000"
  "docker.io":
    endpoint:
      - "http://astronomer-registry-proxy-docker:5000"
  "index.docker.io":
    endpoint:
      - "http://astronomer-registry-proxy-docker:5000"
  "docker.elastic.co":
    endpoint:
      - "http://astronomer-registry-proxy-elastic:5000"
  "registry.k8s.io":
    endpoint:
      - "http://astronomer-registry-proxy-k8s:5000"
  "astrocrpublic.azurecr.io":
    endpoint:
      - "http://astronomer-registry-proxy-astrocrpublic:5000"
"""
    HELPER_DIR.mkdir(parents=True, exist_ok=True)
    K3D_REGISTRY_CONFIG_PATH.write_text(content)
    return K3D_REGISTRY_CONFIG_PATH


# ---------------------------------------------------------------------------
# Docker network + k3d cluster helpers
# ---------------------------------------------------------------------------


def _docker_network_exists(name: str) -> bool:
    return _run(["docker", "network", "inspect", name], check=False).returncode == 0


def _ensure_docker_network(name: str) -> None:
    if _docker_network_exists(name):
        return
    _print(f"Creating Docker network: {name}")
    _run(["docker", "network", "create", name], check=True)


def _k3d_cluster_exists(name: str) -> bool:
    return _run(["k3d", "cluster", "get", name], check=False).returncode == 0


def _delete_k3d_cluster(name: str) -> None:
    if not _k3d_cluster_exists(name):
        return
    _print(f"Deleting k3d cluster: {name}")
    _run(["k3d", "cluster", "delete", name], check=True)


def _k3d_create_cluster(
    *,
    name: str,
    docker_network: str,
    ports: list[str],
    mkcert_root_ca: Path,
    agents: int = 1,
    extra_k3s_args: list[str] | None = None,
    registry_config: Path | None = None,
) -> None:
    """
    Create a k3d cluster and disable traefik.
    Pass extra_k3s_args to forward additional --k3s-arg values (each applied @server:0).
    Pass registry_config to configure containerd pull-through mirrors on each node.
    """
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
    for arg in extra_k3s_args or []:
        cmd.extend(["--k3s-arg", arg])
    for p in ports:
        cmd.extend(["--port", p])

    _print(f"Creating k3d cluster: {name}")
    _debug(f"run: {shlex.join(cmd)}")
    _run(cmd, check=True, capture=True)


def _docker_inspect_ip(container: str) -> str:
    """Return the container IP from `docker inspect` (useful for k3d `*-serverlb` containers)."""
    proc = _run(
        ["docker", "inspect", container, "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
        check=True,
    )
    ip = proc.stdout.strip()
    if not ip:
        raise RuntimeError(f"Could not determine IP for container {container}")
    return ip


def _docker_network_gateway(network: str) -> str:
    """Return a docker network's gateway IP — the host address every container/pod on it can reach.

    For a named network (e.g. `astronomer-net`) this is fixed for the network's lifetime, so (unlike
    the k3d node/LB container IPs) it does NOT drift across OrbStack restarts — which makes it the
    stable target for routing cross-cluster traffic through the host SNI proxy.
    """
    proc = _run(
        ["docker", "network", "inspect", network, "--format", "{{range .IPAM.Config}}{{.Gateway}}{{end}}"],
        check=True,
    )
    gateway = (proc.stdout or "").strip()
    if not gateway:
        raise RuntimeError(f"could not determine the gateway IP of docker network {network!r}")
    return gateway


# ---------------------------------------------------------------------------
# Self-healing node /etc/hosts pin (see configs/local-node-hosts-daemonset.yaml)
# ---------------------------------------------------------------------------
# A node's /etc/hosts is regenerated by Docker on container restart, so a one-shot pin (and k3d
# `--host-alias`, which writes /etc/hosts, not Docker ExtraHosts) is wiped on an OrbStack/Mac restart.
# This DaemonSet re-appends the pin on every node/pod start, keeping node-level cross-cluster
# resolution (e.g. containerd image-pull registry auth) working across restarts. Shared so any local
# setup script can pin the node hosts the same way.
NODE_HOSTS_DAEMONSET_TEMPLATE = Path(__file__).resolve().parents[1] / "configs" / "local-node-hosts-daemonset.yaml"


def _node_hosts_daemonset_manifest(ds_name: str, line: str) -> str:
    """Fill in configs/local-node-hosts-daemonset.yaml for a DaemonSet named `ds_name` that keeps
    `line` present in each node's /etc/hosts (self-healing across Docker/OrbStack restarts)."""
    return NODE_HOSTS_DAEMONSET_TEMPLATE.read_text().format(ds_name=ds_name, hosts_line=line)


def _apply_node_hosts_daemonset(context: str, ds_name: str, line: str) -> None:
    """Apply the self-healing node-/etc/hosts DaemonSet `ds_name` (enforcing `line`) to `context`."""
    manifest = _node_hosts_daemonset_manifest(ds_name, line)
    _run(["kubectl", "--context", context, "-n", "kube-system", "apply", "-f", "-"], stdin=manifest, check=True)
    _print(f"  {context}: {ds_name} re-pins '{line}' on every start (survives restarts)")


# ---------------------------------------------------------------------------
# mkcert / TLS
# ---------------------------------------------------------------------------


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


def _generate_tls_cert(*, mkcert_exe: str, cert_path: Path, key_path: Path, root_ca: Path, sans: list[str]) -> None:
    """
    Generate `cert_path`/`key_path` for `sans` via mkcert, then append mkcert's root CA so the
    cert file is a full chain (matches what `bin/certs.py` does). Callers own SAN computation
    (which subdomains to cover) since that differs per script's topology.
    """
    _print(f"Generating TLS certificates via mkcert (overwrites existing {cert_path.name}/{key_path.name})")
    _run([mkcert_exe, "-install"], check=True)
    _run([mkcert_exe, f"-cert-file={cert_path}", f"-key-file={key_path}", *sans], check=True)

    root_ca_bytes = root_ca.read_bytes()
    cert_bytes = cert_path.read_bytes()
    if root_ca_bytes not in cert_bytes:
        cert_path.write_bytes(cert_bytes + b"\n" + root_ca_bytes)

    if not cert_path.exists() or not key_path.exists():
        raise RuntimeError(f"Failed to generate TLS certs at {cert_path} / {key_path}")


# ---------------------------------------------------------------------------
# kubectl helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# cert-manager (required by the airflow-operator webhooks)
# ---------------------------------------------------------------------------


def _install_cert_manager(context: str) -> None:
    """Install cert-manager CRDs + controller into the cluster behind `context`. Idempotent."""
    _print(f"Installing cert-manager {CERT_MANAGER_VERSION} into {context}")
    _run(["kubectl", "--context", context, "apply", "-f", CERT_MANAGER_MANIFEST_URL], capture=False)


def _pin_cert_manager_to_control_plane(context: str) -> None:
    """Pin cert-manager pods to the k3s control-plane node.

    The kube-apiserver calls cert-manager's admission webhook for Certificate/Issuer
    resources. If the webhook pod lands on an agent node (10.42.1.x), the apiserver
    proxy can't reach it across the Flannel VXLAN overlay in k3d, causing 502 errors.
    Pinning to the control-plane node (10.42.0.x) keeps webhook calls local.
    """
    node_selector_patch = '{"spec":{"template":{"spec":{"nodeSelector":{"node-role.kubernetes.io/control-plane":"true"}}}}}'
    for deployment in ("cert-manager-webhook", "cert-manager-cainjector", "cert-manager"):
        _run(
            [
                "kubectl",
                "--context",
                context,
                "patch",
                "deployment",
                deployment,
                "-n",
                "cert-manager",
                "--type=merge",
                f"--patch={node_selector_patch}",
            ],
            check=False,  # tolerate if a deployment doesn't exist yet
        )


def _wait_for_cert_manager(context: str, timeout_s: int = 180) -> None:
    """Wait for the cert-manager controller + webhook + cainjector deployments to become available."""
    _print(f"Waiting for cert-manager to be ready ({context})")
    for deployment in ("cert-manager", "cert-manager-webhook", "cert-manager-cainjector"):
        _run(
            [
                "kubectl",
                "--context",
                context,
                "-n",
                "cert-manager",
                "wait",
                "--for=condition=available",
                f"deployment/{deployment}",
                f"--timeout={timeout_s}s",
            ],
            capture=False,
        )
    _print(f"cert-manager is ready ({context})")
