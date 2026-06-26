#!/usr/bin/env python3
"""
Convert an existing standalone Astro Runtime Operator cluster into an APC data plane,
stand up a fresh APC control plane next to it, and print the DP→CP registration runbook.

This implements Operator Inheritance — M2 / Task 1
  (astronomer/docs/operator/operator-inheritance/m2-task-1-install-dp.md).

Starting state this script assumes:
- A Kubernetes cluster already runs the standalone Astro Runtime Operator (controller-manager,
  the airflow.apache.org CRDs, cert-manager) with one or more `Airflow` CRs already scheduling
  DAGs. Locally this is the k3d cluster built by `bin/setup-operator-standalone.py`
  (default context `k3d-airflow-dev`, Docker network `airflow-standalone-net`).
- No APC control plane exists yet.

What this script does (and does NOT do):
- CONTROL PLANE: creates a *fresh* k3d cluster in `global.plane.mode: control` on the SAME
  Docker network as the operator cluster, so Houston (CP) and Commander (DP) can reach each
  other over the Docker network.
- DATA PLANE: installs the APC umbrella chart in `global.plane.mode: data` onto the EXISTING
  operator cluster. The `airflow-operator` subchart is SKIPPED (`airflow-operator.enabled: false`)
  so APC stays operator-aware via `global.airflowOperator.enabled: true` WITHOUT reinstalling the
  operator already there — avoiding a cluster-scoped RBAC collision with its existing install.
- REGISTRATION: this script does NOT call `registerCluster`. It prints the exact mutation +
  the computed `metadataUrl` so the operator runs one command to register the DP with the CP.

Hard safety contract — the operator install is never touched:
- never `helm uninstall`, never (re)apply the airflow.apache.org CRDs, never write to the
  operator's namespace, the Airflow CR namespaces, or any `kube-*` namespace.
- the only namespace this script creates/writes in each cluster is the APC platform namespace
  (default `astronomer`).
- a before/after snapshot of `Airflow` CRs is taken to prove the operator's deployments are
  undisturbed.

Modelled on `bin/setup-cp-dp-k3d.py` (shared helpers copied for a standalone script) and
`bin/setup-operator-standalone.py`. Safe to re-run: cluster/secret/helm steps are idempotent.

Notes / constraints:
- We do NOT modify `/etc/hosts` on the local machine. The script prints the entries to add.
- We do NOT install k3d/helm/kubectl/mkcert for you; we validate and fail with actionable hints.
- CP and DP MUST share the same `baseDomain` (Houston's cluster registration + URL helpers
  assume it). This script uses a single `--base-domain` for both, enforcing that by construction.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

# astronomer/ repo root (this file lives at astronomer/bin/setup-operator-dp.py).
REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_DIR = Path.home() / ".local" / "share" / "astronomer-software"
HELPER_BIN_DIR = HELPER_DIR / "bin"
REGISTRY_CONFIG_DIR = HELPER_DIR / "registry-configs"
K3D_REGISTRY_CONFIG_PATH = HELPER_DIR / "k3d-registry.yaml"
REGISTRY_IMAGE = "registry:2"

CP_POSTGRES_NODEPORT = 5432
CP_POSTGRES_USERNAME = "postgres"
CP_POSTGRES_PASSWORD = "postgres"  # noqa: S105

# Namespaces this script must NEVER mutate (operator + system). Guard against footguns.
PROTECTED_NAMESPACE_PREFIXES = ("kube-", "airflow-operator", "cert-manager")


# ---------------------------------------------------------------------------
# Local pull-through registry helpers (shared with bin/setup-cp-dp-k3d.py).
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
            "docker", "run", "-d",
            "--name", spec.name,
            "--network", docker_network,
            "--restart", "always",
            "-p", f"{spec.host_port}:5000",
            "-v", f"{volume_name}:/var/lib/registry",
            "-v", f"{config_path}:/etc/docker/registry/config.yml:ro",
            REGISTRY_IMAGE,
        ]
    )


def _ensure_local_registries(docker_network: str) -> None:
    """Ensure all pull-through registry proxy containers are running on `docker_network`."""
    REGISTRY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for spec in _REGISTRY_SPECS:
        (REGISTRY_CONFIG_DIR / f"{spec.name}.yml").write_text(_registry_docker_config(spec))
        _ensure_registry(spec, docker_network)


def _get_registry_config_path(_docker_network: str) -> Path:
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
# Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ControlPlane:
    cluster_name: str  # k3d cluster name (context is f"k3d-{cluster_name}")
    https_port: int
    http_port: int


@dataclass(frozen=True)
class OperatorDataPlane:
    """The pre-existing operator cluster we layer the DP onto. We do NOT create this cluster."""
    cluster_name: str   # k3d cluster name, e.g. "airflow-dev" (context f"k3d-{cluster_name}")
    context: str        # kube context, e.g. "k3d-airflow-dev"
    domain_prefix: str  # APC DP subdomain prefix, e.g. "dp01"


@dataclass
class Survey:
    """Read-only inventory of the operator cluster, used to drive DP value toggles."""
    operator_namespace: str | None = None
    operator_image: str | None = None
    airflow_crd_count: int = 0
    has_cert_manager: bool = False
    has_servicemonitor_crd: bool = False
    has_prometheus: bool = False
    has_log_shipper: bool = False
    has_elasticsearch: bool = False
    airflow_crs: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class Settings:
    base_domain: str
    namespace: str
    release_name: str
    docker_network: str
    control_plane: ControlPlane
    data_plane: OperatorDataPlane
    tls_secret_name: str
    mkcert_root_ca_secret_name: str
    mkcert_root_ca_secret_key: str
    helm_timeout: str
    helm_debug: bool


# ---------------------------------------------------------------------------
# Logging + command runner (shared with bin/setup-cp-dp-k3d.py).
# ---------------------------------------------------------------------------


def _print(msg: str) -> None:
    print(msg, flush=True)


def _debug_enabled() -> bool:
    return os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"}


def _debug(msg: str) -> None:
    if _debug_enabled():
        _print(f"DEBUG: {msg}")


def _ts() -> str:
    return time.strftime("%H:%M:%S")


@dataclass(frozen=True)
class MilestoneHandle:
    idx: int


class Milestones:
    """Minimal live output + a final ✅/❌ summary table (same UX as the sibling setup scripts)."""

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
                "idx": h.idx, "title": title, "status": "running",
                "started_at": time.monotonic(), "ended_at": None,
                "duration_s": None, "detail": "", "error": "",
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
        if self._active is not None:
            self.fail(self._active, error=error)

    def skip(self, title: str, *, reason: str) -> None:
        self._idx += 1
        self._rows.append(
            {
                "idx": self._idx, "title": title, "status": "skipped",
                "started_at": None, "ended_at": None,
                "duration_s": 0.0, "detail": reason, "error": "",
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
            status = str(row["status"])
            status_cell = {
                "success": "✅ Success", "failure": "❌ Failed",
                "skipped": "⏭️ Skipped", "running": "⏳ Running",
            }.get(status, status)
            duration_s = row.get("duration_s")
            duration_cell = f"{duration_s:.1f}s" if isinstance(duration_s, (int, float)) else "-"
            detail = _one_line(str(row.get("detail") or ""))
            error = _one_line(str(row.get("error") or ""))
            details_cell = detail + ((" " if detail else "") + error if error else "")
            rows.append(
                [
                    str(int(row["idx"])),
                    _truncate(_one_line(str(row["title"])), 70),
                    status_cell,
                    duration_cell,
                    _truncate(details_cell, 90),
                ]
            )

        headers = ["#", "Milestone", "Status", "Duration", "Details"]
        widths = [len(h) for h in headers]
        for r in rows:
            for i, cell in enumerate(r):
                widths[i] = max(widths[i], len(cell))

        def _sep() -> str:
            return "+".join(["-" * (w + 2) for w in widths]).join(["+", "+"])

        def _fmt_row(cells: list[str]) -> str:
            return "|" + "|".join(f" {cells[i].ljust(widths[i])} " for i in range(len(cells))) + "|"

        _print("\nMilestones summary:\n")
        _print(_sep())
        _print(_fmt_row(headers))
        _print(_sep())
        for r in rows:
            _print(_fmt_row(r))
        _print(_sep())

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
    return (proc.stdout or "").strip() or None


def _require_executable(exe: str, *, hint: str) -> None:
    if _which(exe) is None:
        raise RuntimeError(f"Missing required executable `{exe}`. {hint}")


def _validate_prereqs() -> None:
    _require_executable("docker", hint="Install Docker Desktop/OrbStack and ensure `docker` works.")
    _require_executable("k3d", hint="Install k3d (e.g. `brew install k3d` on macOS).")
    _require_executable("kubectl", hint="Install kubectl and ensure it is in PATH.")
    _require_executable("helm", hint="Install helm and ensure it is in PATH.")


# ---------------------------------------------------------------------------
# Docker network + k3d helpers
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


def _detect_operator_network(dp_node_container: str) -> str | None:
    """Return the non-default Docker network the operator node container is attached to."""
    nets = [n for n in _container_networks(dp_node_container) if n not in {"bridge", "host", "none"}]
    return nets[0] if nets else None


def _host_port_free(port: int) -> bool:
    """Return True if `port` can be bound on the host (i.e. nothing else is using it)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def _pick_free_host_port(preferred: int, *, avoid: set[int]) -> int:
    """Return `preferred` if free, else the next free host port above it (skipping `avoid`)."""
    port = preferred
    while port in avoid or not _host_port_free(port):
        port += 1
    return port


def _k3d_create_cluster(
    *,
    name: str,
    docker_network: str,
    ports: list[str],
    mkcert_root_ca: Path,
    extra_k3s_args: list[str] | None = None,
    registry_config: Path | None = None,
) -> None:
    """Create a k3d cluster with traefik disabled and the mkcert root CA mounted on every node."""
    volume = f"{mkcert_root_ca}:/etc/ssl/certs/mkcert-rootCA.pem@server:*;agent:*"
    cmd = [
        "k3d", "cluster", "create", name,
        "--network", docker_network,
        "--agents", "0",
        "--k3s-arg", "--disable=traefik@server:0",
        "--volume", volume,
    ]
    if registry_config is not None:
        cmd.extend(["--registry-config", str(registry_config)])
    for arg in extra_k3s_args or []:
        cmd.extend(["--k3s-arg", arg])
    for p in ports:
        cmd.extend(["--port", p])
    _print(f"Creating k3d cluster: {name}")
    _run(cmd, check=True, capture=True)


# ---------------------------------------------------------------------------
# mkcert / TLS
# ---------------------------------------------------------------------------


def _mkcert_path() -> str:
    helper = HELPER_BIN_DIR / "mkcert"
    return str(helper) if helper.exists() else "mkcert"


def _mkcert_caroot(mkcert_exe: str) -> Path:
    proc = _run([mkcert_exe, "-CAROOT"], check=True)
    caroot = Path(proc.stdout.strip())
    root_ca = caroot / "rootCA.pem"
    if not root_ca.exists():
        raise RuntimeError(f"mkcert rootCA.pem not found at: {root_ca}")
    return root_ca


def _ensure_tls_certs(settings: Settings) -> tuple[Path, Path, Path]:
    """
    Generate `astronomer-tls.{pem,key}` with SANs for the CP and the DP subdomain:
      <baseDomain>, *.<baseDomain>, <dpPrefix>.<baseDomain>, *.<dpPrefix>.<baseDomain>
    Returns (cert_path, key_path, mkcert_root_ca_path).
    """
    mkcert_exe = _mkcert_path()
    _require_executable(
        mkcert_exe,
        hint="Install mkcert (or run `python3 bin/install-ci-tools.py` to install the repo-pinned version).",
    )
    cert_dir = HELPER_DIR / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "astronomer-tls.pem"
    key_path = cert_dir / "astronomer-tls.key"

    root_ca = _mkcert_caroot(mkcert_exe)

    _print("Generating TLS certificates via mkcert (overwrites existing astronomer-tls.{pem,key})")
    _run([mkcert_exe, "-install"], check=True)

    base = settings.base_domain
    dp = settings.data_plane.domain_prefix
    sans = [base, f"*.{base}", f"{dp}.{base}", f"*.{dp}.{base}"]
    _run([mkcert_exe, f"-cert-file={cert_path}", f"-key-file={key_path}", *sans], check=True)

    # Append mkcert root CA for a full chain (matches bin/certs.py / setup-cp-dp-k3d.py).
    root_ca_bytes = root_ca.read_bytes()
    cert_bytes = cert_path.read_bytes()
    if root_ca_bytes not in cert_bytes:
        cert_path.write_bytes(cert_bytes + b"\n" + root_ca_bytes)

    if not cert_path.exists() or not key_path.exists():
        raise RuntimeError(f"Failed to generate TLS certs at {cert_path} / {key_path}")
    return cert_path, key_path, root_ca


# ---------------------------------------------------------------------------
# kubectl helpers
# ---------------------------------------------------------------------------


def _assert_safe_namespace(namespace: str) -> None:
    """Fail loudly if asked to use a protected (operator/system) namespace for APC platform install."""
    for prefix in PROTECTED_NAMESPACE_PREFIXES:
        if namespace == prefix or namespace.startswith(prefix):
            raise RuntimeError(
                f"Refusing to install the APC platform into protected namespace '{namespace}'. "
                "This namespace belongs to the operator/system; pick a dedicated platform namespace "
                "(default: astronomer)."
            )


def _kubectl_apply_yaml(context: str, yaml_text: str) -> None:
    _run(["kubectl", "--context", context, "apply", "-f", "-"], check=True, stdin=yaml_text)


def _kubectl_create_namespace(context: str, namespace: str) -> None:
    proc = _run(["kubectl", "--context", context, "create", "namespace", namespace], check=False)
    if proc.returncode == 0 or "AlreadyExists" in (proc.stderr or ""):
        return
    raise CommandError(f"Failed to create namespace {namespace} (context={context}): {(proc.stderr or '').strip()}")


def _kubectl_apply_tls_secret(
    *, context: str, namespace: str, secret_name: str, cert_path: Path, key_path: Path
) -> None:
    secret_yaml = _run(
        [
            "kubectl", "--context", context, "-n", namespace,
            "create", "secret", "tls", secret_name,
            f"--cert={cert_path}", f"--key={key_path}",
            "--dry-run=client", "-o", "yaml",
        ],
        check=True,
    ).stdout
    _kubectl_apply_yaml(context, secret_yaml)


def _kubectl_apply_generic_secret_from_file(
    *, context: str, namespace: str, secret_name: str, key: str, file_path: Path
) -> None:
    secret_yaml = _run(
        [
            "kubectl", "--context", context, "-n", namespace,
            "create", "secret", "generic", secret_name,
            f"--from-file={key}={file_path}",
            "--dry-run=client", "-o", "yaml",
        ],
        check=True,
    ).stdout
    _kubectl_apply_yaml(context, secret_yaml)


def _create_astronomer_bootstrap_secret_postgres(*, context: str, namespace: str, pg_host: str) -> None:
    """Create/update the astronomer-bootstrap secret pointing the DP at the CP's shared postgres."""
    conn = f"postgres://{CP_POSTGRES_USERNAME}:{CP_POSTGRES_PASSWORD}@{pg_host}:{CP_POSTGRES_NODEPORT}"
    secret_yaml = _run(
        [
            "kubectl", "--context", context, "-n", namespace,
            "create", "secret", "generic", "astronomer-bootstrap",
            f"--from-literal=connection={conn}",
            "--dry-run=client", "-o", "yaml",
        ],
        check=True,
    ).stdout
    _kubectl_apply_yaml(context, secret_yaml)
    _debug(f"astronomer-bootstrap secret set with postgres connection to {pg_host}")


def _kubectl_get_service_lb_ip(context: str, namespace: str, service: str) -> str:
    proc = _run(
        [
            "kubectl", "--context", context, "-n", namespace,
            "get", "svc", service,
            "-o", "jsonpath={.status.loadBalancer.ingress[0].ip}",
        ],
        check=True,
    )
    ip = proc.stdout.strip()
    if not ip:
        raise RuntimeError(f"Service {namespace}/{service} has no LoadBalancer ingress IP (context={context})")
    return ip


def _docker_inspect_ip(container: str) -> str:
    proc = _run(
        ["docker", "inspect", container, "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
        check=True,
    )
    ip = proc.stdout.strip()
    if not ip:
        raise RuntimeError(f"Could not determine IP for container {container}")
    return ip


def _ensure_container_hosts_mapping(container: str, ip: str, hostname: str) -> None:
    sh = (
        "set -eu; "
        + f"grep -qE '^[[:space:]]*{ip}[[:space:]]+.*\\b{hostname}\\b' /etc/hosts "
        + f"|| echo '{ip} {hostname}' >> /etc/hosts"
    )
    _run(["docker", "exec", container, "sh", "-c", sh], check=True)


def _ensure_dp_node_houston_hosts_pin(settings: Settings) -> None:
    """Pin houston.<baseDomain> -> CP ingress LB IP in the DP node's /etc/hosts (node-level DNS for image pulls)."""
    cp = settings.control_plane
    cp_context = f"k3d-{cp.cluster_name}"
    cp_nginx_svc = f"{settings.release_name}-cp-nginx"
    cp_nginx_lb_ip = _kubectl_get_service_lb_ip(cp_context, settings.namespace, cp_nginx_svc)
    houston_host = f"houston.{settings.base_domain}"
    node_container = f"k3d-{settings.data_plane.cluster_name}-server-0"
    _ensure_container_hosts_mapping(node_container, cp_nginx_lb_ip, houston_host)
    _debug(f"Ensured /etc/hosts pin on {node_container}: {cp_nginx_lb_ip} {houston_host}")


# ---------------------------------------------------------------------------
# Helm
# ---------------------------------------------------------------------------


def _helm_dependency_update(chart_dir: Path) -> None:
    _print("Running `helm dependency update`")
    _run(["helm", "dependency", "update", str(chart_dir)], check=True)


def _helm_upgrade_install(
    *,
    context: str,
    chart_dir: Path,
    release_name: str,
    namespace: str,
    values_file: Path,
    extra_values_files: list[Path],
    timeout: str,
    debug: bool,
    wait: bool = False,
) -> None:
    """
    `helm upgrade --install`. NOTE: `wait` defaults to FALSE on purpose.

    With `--wait`, a fresh install deadlocks: Helm waits for main resources Ready *before*
    running `post-install` hooks, but Houston's DB-migration (which creates the Cluster/Deployment
    tables) is a `post-install` hook, and the Prometheus `filesd-reloader` sidecar (a main resource)
    crashes until those tables exist. So `--wait` blocks on a pod that needs a hook that `--wait`
    is blocking. Without `--wait`, Helm still awaits the post-install migration *Job* (which
    self-gates on the DB), the schema gets created, and the reloader recovers. We then wait on the
    specific Deployments we need via `_wait_for_deployments_available()`.
    """
    cmd = [
        "helm", "upgrade", "--install", release_name, str(chart_dir),
        "--namespace", namespace,
        "--kube-context", context,
        "--values", str(values_file),
        "--timeout", timeout,
    ]
    if wait:
        cmd.append("--wait")
    for extra in extra_values_files:
        cmd.extend(["--values", str(extra)])
    if debug:
        cmd.append("--debug")
    _print(f"Helm upgrade/install ({context}): {release_name} in ns={namespace}")
    _run(cmd, check=True, capture=False)


def _wait_for_deployments_available(context: str, namespace: str, *, timeout: str = "600s") -> None:
    """
    Wait for all Deployments in `namespace` to be Available.

    Deliberately scoped to Deployments — we do NOT wait on the Prometheus StatefulSet, whose
    `filesd-reloader` sidecar crashes until Houston's post-install migration creates the
    Cluster/Deployment tables. Houston, nginx, Commander, Astro UI are all Deployments, so this
    covers everything DP↔CP registration needs without re-introducing the deadlock.
    """
    _print(f"Waiting for Deployments to be Available ({context}, ns={namespace})")
    _run(
        ["kubectl", "--context", context, "-n", namespace, "wait",
         "--for=condition=Available", "deploy", "--all", f"--timeout={timeout}"],
        check=True, capture=False,
    )


# ---------------------------------------------------------------------------
# DNS reconcile (reuse the existing helper, same env contract as setup-cp-dp-k3d.py)
# ---------------------------------------------------------------------------


def _run_dns_reconcile(settings: Settings) -> None:
    script = REPO_ROOT / "bin" / "reconcile-k3d-orbstack-network.py"
    cp = settings.control_plane
    dp = settings.data_plane
    env = dict(os.environ)
    env.update(
        {
            "CP_CONTEXT": f"k3d-{cp.cluster_name}",
            "DP_CONTEXT": dp.context,
            "PLATFORM_NAMESPACE": settings.namespace,
            "BASE_DOMAIN": settings.base_domain,
            "DP_DOMAIN_PREFIX": dp.domain_prefix,
            "DP_NODE_CONTAINER": f"k3d-{dp.cluster_name}-server-0",
            "DP_AGENTS": "0",
            "CP_INGRESS_SERVICE": f"{settings.release_name}-cp-nginx",
        }
    )
    _print(f"Reconciling k3d cross-cluster DNS + node-level hosts pins (DP={dp.cluster_name})")
    _run([sys.executable, str(script)], check=True, env=env, capture=False)


# ---------------------------------------------------------------------------
# Survey — read-only inventory of the operator cluster
# ---------------------------------------------------------------------------


def _k(context: str, *args: str, check: bool = False) -> str:
    """Run a read-only kubectl against `context` and return stdout (empty on error)."""
    proc = _run(["kubectl", "--context", context, "--request-timeout=20s", *args], check=check)
    return (proc.stdout or "").strip()


def _survey_operator_cluster(context: str) -> Survey:
    """Inventory operator install, CRDs, observability, and Airflow CRs. Read-only; best-effort."""
    s = Survey()

    # airflow.apache.org CRDs
    crds = _k(context, "get", "crds", "-o", "name")
    s.airflow_crd_count = sum(1 for line in crds.splitlines() if "airflow.apache.org" in line)
    s.has_servicemonitor_crd = "servicemonitors.monitoring.coreos.com" in crds

    # operator controller deployment (search all namespaces by name)
    deploys = _k(context, "get", "deploy", "-A", "-o", "json")
    try:
        for item in json.loads(deploys or "{}").get("items", []):
            name = item["metadata"]["name"]
            ns = item["metadata"]["namespace"]
            if "airflow-operator" in name or "airflow-operator" in ns:
                s.operator_namespace = ns
                containers = item["spec"]["template"]["spec"].get("containers", [])
                if containers:
                    s.operator_image = containers[0].get("image")
                break
    except (json.JSONDecodeError, KeyError):
        pass

    # cert-manager
    s.has_cert_manager = bool(_k(context, "get", "ns", "cert-manager", "-o", "name"))

    # observability heuristics across the cluster (exclude k3s system namespaces)
    all_workloads = _k(context, "get", "deploy,statefulset,daemonset", "-A", "-o", "json")
    try:
        for item in json.loads(all_workloads or "{}").get("items", []):
            ns = item["metadata"]["namespace"]
            name = item["metadata"]["name"].lower()
            if ns.startswith("kube-"):
                continue
            if "prometheus" in name:
                s.has_prometheus = True
            if any(t in name for t in ("vector", "fluent-bit", "fluentbit", "fluentd", "filebeat")):
                s.has_log_shipper = True
            if "elasticsearch" in name or "opensearch" in name:
                s.has_elasticsearch = True
    except (json.JSONDecodeError, KeyError):
        pass

    # Airflow CRs
    crs = _k(context, "get", "airflows.airflow.apache.org", "-A", "-o", "json")
    try:
        for item in json.loads(crs or "{}").get("items", []):
            spec = item.get("spec", {})
            s.airflow_crs.append(
                {
                    "namespace": item["metadata"]["namespace"],
                    "name": item["metadata"]["name"],
                    "executor": str(spec.get("executor", "")),
                    "runtimeVersion": str(spec.get("runtimeVersion", spec.get("airflowVersion", ""))),
                    "image": str(spec.get("image", "")),
                }
            )
    except (json.JSONDecodeError, KeyError):
        pass

    return s


def _print_survey(s: Survey, context: str) -> None:
    _print(f"\nOperator cluster survey (context={context}):")
    _print(f"  • airflow.apache.org CRDs ........ {s.airflow_crd_count}")
    _print(f"  • operator controller namespace .. {s.operator_namespace or '<not found>'}")
    _print(f"  • operator image ................. {s.operator_image or '<unknown>'}")
    _print(f"  • cert-manager present ........... {s.has_cert_manager}")
    _print(f"  • ServiceMonitor CRD present ..... {s.has_servicemonitor_crd}")
    _print(f"  • existing Prometheus ............ {s.has_prometheus}")
    _print(f"  • existing log shipper ........... {s.has_log_shipper}")
    _print(f"  • existing Elasticsearch ......... {s.has_elasticsearch}")
    _print(f"  • Airflow CRs .................... {len(s.airflow_crs)}")
    for cr in s.airflow_crs:
        _print(f"      - {cr['namespace']}/{cr['name']}  executor={cr['executor']}  runtime={cr['runtimeVersion']}")
    if s.airflow_crd_count == 0 or s.operator_namespace is None:
        _print(
            "\n  ⚠️  No operator install detected. This script is for clusters that ALREADY run the "
            "Astro Runtime Operator. If this is wrong, double-check --operator-context."
        )


def _snapshot_airflow_crs(context: str) -> str:
    """Stable identity snapshot of all Airflow CRs (ns/name/uid/resourceVersion) for before/after diff."""
    jsonpath = (
        "jsonpath={range .items[*]}{.metadata.namespace}/{.metadata.name}="
        "{.metadata.uid}@{.metadata.generation}{\"\\n\"}{end}"
    )
    out = _k(context, "get", "airflows.airflow.apache.org", "-A", "-o", jsonpath)
    return "\n".join(sorted(line for line in out.splitlines() if line))


# ---------------------------------------------------------------------------
# Values files
# ---------------------------------------------------------------------------


def _write_values_file(path: Path, content: str) -> None:
    path.write_text(content)


# CONTROL PLANE: install the airflow-operator subchart but NEUTRALIZED. The CP doesn't run airflow
# workloads, so we keep `global.airflowOperator.enabled: true` (Houston/Commander operator mode)
# while the subchart applies no CRDs, no webhooks, and a 0-replica controller. The CP is a fresh
# cluster, so its cluster-scoped operator RBAC collides with nothing.
_OPERATOR_SUBCHART_NEUTRALIZED = """\
airflow-operator:
  crd:
    create: false
  certManager:
    enabled: false
  webhooks:
    enabled: false
  manager:
    replicas: 0
"""

# DATA PLANE: SKIP the airflow-operator subchart entirely. The operator cluster already runs a
# standalone operator that OWNS the cluster-scoped CRDs and RBAC (ClusterRole
# `airflow-operator-manager-role`, etc.), so rendering the subchart would fail the helm install
# with an ownership collision. `airflow-operator.enabled: false` short-circuits the umbrella's
# dependency condition (see Chart.yaml) so none of the subchart's resources render, while
# `global.airflowOperator.enabled: true` (set in globals) keeps Commander's airflow.apache.org RBAC.
_OPERATOR_SUBCHART_DISABLED = """\
airflow-operator:
  enabled: false
"""

# The Prometheus configmap-reloader sidecar OOMs at the chart's default 25Mi limit on these local
# clusters (astronomer/values.yaml `prometheus.configMapReloader.resources`). Bump it on both planes.
# Harmless when Prometheus is disabled (the override is simply ignored).
_PROMETHEUS_RELOADER_OVERRIDE = """\
prometheus:
  configMapReloader:
    resources:
      requests:
        cpu: 100m
        memory: 64Mi
      limits:
        cpu: 100m
        memory: 128Mi
"""


def _cp_values_yaml(settings: Settings) -> str:
    """Control-plane values (global.plane.mode: control), operator-aware, subchart neutralized."""
    return f"""\
global:
  baseDomain: {settings.base_domain}
  plane:
    mode: control
    domainPrefix: ""
  tlsSecret: {settings.tls_secret_name}
  postgresql:
    enabled: true
  privateCaCerts:
    - {settings.mkcert_root_ca_secret_name}
  nats:
    enabled: true
    replicas: 1
  networkPolicy:
    enabled: false
  defaultDenyNetworkPolicy: false
  deployRollbackEnabled: true
  taskUsageMetricsEnabled: true
  daemonsetLogging:
    enabled: true
  dagOnlyDeployment:
    enabled: true
  airflowOperator:
    enabled: true

tags:
  platform: true
  postgresql: true

astronomer:
  astroUI:
    replicas: 1
  houston:
    replicas: 1
    worker:
      replicas: 1
    config:
      emailConfirmation:
        enabled: false
      publicSignups:
        enabled: false
      cors:
        allowedOrigins:
          - "https://app.{settings.base_domain}"
      auth:
        local:
          enabled: true
      deployments:
        configureDagDeployment: true
        hardDeleteDeployment: true
  commander:
    replicas: 1
  registry: {{}}

nginx:
  replicas: 1
  replicasDefaultBackend: 1

nats:
  cluster:
    enabled: false
    replicas: 1
  resources:
    requests:
      cpu: "50m"
      memory: "64Mi"

elasticsearch:
  common:
    env:
      NUMBER_OF_MASTERS: "1"
  master:
    replicas: 1
    heapMemory: 128m
    resources:
      requests:
        cpu: "100m"
        memory: 256Mi
  data:
    replicas: 1
    heapMemory: 256m
    resources:
      requests:
        cpu: "100m"
        memory: 512Mi
  client:
    replicas: 1
    heapMemory: 128m
    resources:
      requests:
        cpu: "100m"
        memory: 256Mi
  images:
    es:
      repository: docker.elastic.co/elasticsearch/elasticsearch
      tag: "8.18.6"

postgresql:
  postgresqlUsername: {CP_POSTGRES_USERNAME}
  postgresqlPassword: {CP_POSTGRES_PASSWORD}
  service:
    type: NodePort
    nodePort: {CP_POSTGRES_NODEPORT}

{_PROMETHEUS_RELOADER_OVERRIDE}
{_OPERATOR_SUBCHART_NEUTRALIZED}"""


def _operator_dp_values_yaml(settings: Settings, survey: Survey) -> str:
    """
    Data-plane values (global.plane.mode: data) for the EXISTING operator cluster.

    Differs from setup-cp-dp-k3d.py's DP values in one critical way: the airflow-operator
    subchart is DISABLED (`airflow-operator.enabled: false`), because the operator is already
    present and owns the cluster-scoped CRDs/RBAC — installing it again collides. We still set
    `global.airflowOperator.enabled: true` so Commander gets airflow.apache.org RBAC.
    Observability toggles are driven by the survey so we don't duplicate the customer's stack.
    """
    dp = settings.data_plane
    # Bring APC's own DP observability only when the cluster doesn't already have it.
    prometheus_enabled = "false" if survey.has_prometheus else "true"
    logging_enabled = "false" if survey.has_log_shipper else "true"
    return f"""\
global:
  baseDomain: {settings.base_domain}
  plane:
    mode: data
    domainPrefix: {dp.domain_prefix}
  tlsSecret: {settings.tls_secret_name}
  postgresql:
    enabled: false
  privateCaCerts:
    - {settings.mkcert_root_ca_secret_name}
  nats:
    enabled: true
    replicas: 1
  networkPolicy:
    enabled: false
  defaultDenyNetworkPolicy: false
  deployRollbackEnabled: true
  taskUsageMetricsEnabled: true
  daemonsetLogging:
    enabled: {logging_enabled}
  dagOnlyDeployment:
    enabled: true
  nginx:
    enabled: true
  prometheus:
    enabled: {prometheus_enabled}
  airflowOperator:
    enabled: true

tags:
  platform: true
  postgresql: false

{_OPERATOR_SUBCHART_DISABLED}
astronomer:
  commander:
    replicas: 1
  registry: {{}}

nginx:
  replicas: 1
  replicasDefaultBackend: 1

nats:
  cluster:
    enabled: false
    replicas: 1
  resources:
    requests:
      cpu: "50m"
      memory: "64Mi"

elasticsearch:
  common:
    env:
      NUMBER_OF_MASTERS: "1"
  master:
    replicas: 1
    heapMemory: 128m
    resources:
      requests:
        cpu: "100m"
        memory: 256Mi
  data:
    replicas: 1
    heapMemory: 256m
    resources:
      requests:
        cpu: "100m"
        memory: 512Mi
  client:
    replicas: 1
    heapMemory: 128m
    resources:
      requests:
        cpu: "100m"
        memory: 256Mi
  images:
    es:
      repository: docker.elastic.co/elasticsearch/elasticsearch
      tag: "8.18.6"

{_PROMETHEUS_RELOADER_OVERRIDE}"""


# ---------------------------------------------------------------------------
# Registration runbook (printed, NOT executed — the operator runs this).
# ---------------------------------------------------------------------------


def _discover_dp_ingress_hosts(settings: Settings) -> list[str]:
    """Best-effort: list the hostnames the DP nginx Ingress serves (to locate the metadata host)."""
    out = _k(
        settings.data_plane.context,
        "-n", settings.namespace,
        "get", "ingress", "-o",
        "jsonpath={range .items[*]}{range .spec.rules[*]}{.host}{\"\\n\"}{end}{end}",
    )
    return sorted({h for h in out.splitlines() if h})


def _print_registration_runbook(settings: Settings) -> None:
    """
    Print everything the operator needs to register this DP with the CP. We do NOT call
    registerCluster — registration is performed manually with a SYSTEM_ADMIN token.
    """
    base = settings.base_domain
    dp = settings.data_plane
    dp_serverlb = f"k3d-{dp.cluster_name}-serverlb"
    try:
        dp_ip = _docker_inspect_ip(dp_serverlb)
    except Exception:  # noqa: BLE001
        dp_ip = "<dp-serverlb-ip>"

    hosts = _discover_dp_ingress_hosts(settings)
    # Commander's /metadata is served on the DP ingress. Prefer a discovered commander host;
    # otherwise fall back to the conventional <prefix>.<baseDomain> deployments host.
    commander_host = next((h for h in hosts if h.startswith("commander.")), None)
    metadata_host = commander_host or f"{dp.domain_prefix}.{base}"
    metadata_url = f"https://{metadata_host}"

    _print("\n" + "=" * 78)
    _print("DP → CP REGISTRATION (run this yourself — this script does NOT call registerCluster)")
    _print("=" * 78)
    _print("\n1) Make sure your host /etc/hosts maps the DP ingress (see entries printed above), so")
    _print(f"   `{metadata_host}` resolves to the DP nginx at {dp_ip}.")
    _print("\n2) Sanity-check Commander's metadata endpoint is reachable and well-formed:")
    _print(f"     curl -sk {metadata_url}/metadata | jq .")
    if hosts:
        _print(f"\n   (DP ingress currently serves: {', '.join(hosts)})")
    else:
        _print("\n   (No DP Ingress hosts discovered yet — confirm the commander/metadata host before registering.)")
    _print("\n3) Get a SYSTEM_ADMIN auth token for the CP Houston (local auth is enabled), then call")
    _print(f"   the mutation against https://houston.{base}/v1 :\n")
    _print(f"""   mutation RegisterDataPlane {{
     registerCluster(
       name: "{dp.cluster_name}"
       metadataUrl: "{metadata_url}"
     ) {{
       id
       name
       baseDomain
       status
     }}
   }}""")
    _print(f"\n   The registered cluster's baseDomain MUST equal the CP's helm.baseDomain ({base}).")
    _print("=" * 78)


def _print_host_etc_hosts_instructions(settings: Settings) -> None:
    """Print recommended host /etc/hosts entries (CP + DP ingress via the k3d serverlb IPs)."""
    base = settings.base_domain
    cp = settings.control_plane
    dp = settings.data_plane
    _print("\nAdd the following entries to your host `/etc/hosts`:\n")
    try:
        dp_ip = _docker_inspect_ip(f"k3d-{dp.cluster_name}-serverlb")
        prefix = dp.domain_prefix
        _print(
            f"{dp_ip} {prefix}.{base} deployments.{prefix}.{base} registry.{prefix}.{base} "
            f"commander.{prefix}.{base} prometheus.{prefix}.{base} elasticsearch.{prefix}.{base}"
        )
    except Exception as e:  # noqa: BLE001
        _print(f"# (could not determine DP serverlb IP: {e})")
    try:
        cp_ip = _docker_inspect_ip(f"k3d-{cp.cluster_name}-serverlb")
        _print(
            f"{cp_ip} {base} app.{base} houston.{base} grafana.{base} prometheus.{base} "
            f"elasticsearch.{base} alertmanager.{base} registry.{base}"
        )
    except Exception as e:  # noqa: BLE001
        _print(f"# (could not determine CP serverlb IP: {e})")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert an existing standalone Airflow-operator cluster into an APC data plane "
            "and stand up a fresh control plane."
        ),
    )
    parser.add_argument("--operator-context", default="k3d-airflow-dev",
                        help="kube context of the EXISTING operator cluster (becomes the DP). Default: %(default)s")
    parser.add_argument("--operator-cluster-name", default=None,
                        help="k3d cluster name of the operator cluster. Default: --operator-context without any leading 'k3d-'.")
    parser.add_argument("--base-domain", default="localtest.me",
                        help="Shared baseDomain for CP and DP (must match). Default: %(default)s")
    parser.add_argument("--namespace", default="astronomer", help="APC platform namespace. Default: %(default)s")
    parser.add_argument("--release-name", default="astronomer", help="Helm release name. Default: %(default)s")
    parser.add_argument("--docker-network", default=None,
                        help="Docker network the CP joins. Default: auto-detected from the operator cluster.")
    parser.add_argument("--cp-cluster-name", default="cp01",
                        help="k3d cluster name for the new control plane. Default: %(default)s")
    parser.add_argument("--cp-https-port", type=int, default=8443,
                        help="Preferred host HTTPS port for the CP loadbalancer; auto-bumped to the next free "
                             "port if taken (the operator cluster already publishes 8443). Default: %(default)s")
    parser.add_argument("--cp-http-port", type=int, default=8080,
                        help="Preferred host HTTP port for the CP loadbalancer; auto-bumped to the next free "
                             "port if taken (the operator cluster already publishes 8080). Default: %(default)s")
    parser.add_argument("--dp-domain-prefix", default="dp01", help="APC DP subdomain prefix. Default: %(default)s")

    parser.add_argument("--tls-secret-name", default="astronomer-tls")
    parser.add_argument("--mkcert-root-ca-secret-name", default="mkcert-root-ca")
    parser.add_argument("--mkcert-root-ca-secret-key", default="cert.pem")

    parser.add_argument("--helm-timeout", default=os.environ.get("HELM_TIMEOUT", "60m"))
    parser.add_argument("--helm-debug", action="store_true")
    parser.add_argument("--helm-deps-update", action="store_true",
                        help="Run `helm dependency update` before installing (off by default; local charts are vendored).")
    parser.add_argument("--helm-values", action="append", default=[], dest="helm_values", metavar="FILE",
                        help="Extra Helm values file passed to both CP and DP installs (repeatable).")
    parser.add_argument("--values-dir", default="",
                        help="Directory to write cp-values.yaml / dp-values.yaml. Defaults to a temp directory.")

    parser.add_argument("--recreate-cp-cluster", action="store_true", help="Delete and recreate the CP k3d cluster if it exists.")
    parser.add_argument("--no-local-registry", action="store_true", help="Skip the pull-through registry proxy setup.")

    parser.add_argument("--survey-only", action="store_true", help="Run the read-only operator-cluster survey and exit.")
    parser.add_argument("--skip-certs", action="store_true")
    parser.add_argument("--skip-cp", action="store_true", help="Skip creating/installing the control plane.")
    parser.add_argument("--skip-dp", action="store_true", help="Skip installing the data plane onto the operator cluster.")
    parser.add_argument("--skip-dns-reconcile", action="store_true")
    return parser.parse_args()


def main() -> int:  # noqa: C901
    args = parse_args()
    ms = Milestones()

    operator_cluster_name = args.operator_cluster_name or (
        args.operator_context[len("k3d-"):] if args.operator_context.startswith("k3d-") else args.operator_context
    )
    dp = OperatorDataPlane(
        cluster_name=operator_cluster_name,
        context=args.operator_context,
        domain_prefix=args.dp_domain_prefix,
    )
    cp = ControlPlane(cluster_name=args.cp_cluster_name, https_port=args.cp_https_port, http_port=args.cp_http_port)

    # Resolve the Docker network: prefer explicit flag, else auto-detect from the operator node.
    dp_node_container = f"k3d-{dp.cluster_name}-server-0"
    docker_network = args.docker_network or _detect_operator_network(dp_node_container) or "airflow-standalone-net"

    settings = Settings(
        base_domain=args.base_domain,
        namespace=args.namespace,
        release_name=args.release_name,
        docker_network=docker_network,
        control_plane=cp,
        data_plane=dp,
        tls_secret_name=args.tls_secret_name,
        mkcert_root_ca_secret_name=args.mkcert_root_ca_secret_name,
        mkcert_root_ca_secret_key=args.mkcert_root_ca_secret_key,
        helm_timeout=args.helm_timeout,
        helm_debug=bool(args.helm_debug),
    )

    try:
        _assert_safe_namespace(settings.namespace)

        h = ms.start("Validate prerequisites (docker/k3d/kubectl/helm)")
        _validate_prereqs()
        ms.done(h)

        # Step: survey the operator cluster (read-only) + snapshot Airflow CRs for a before/after diff.
        h = ms.start(f"Survey operator cluster ({dp.context})")
        survey = _survey_operator_cluster(dp.context)
        _print_survey(survey, dp.context)
        crs_before = _snapshot_airflow_crs(dp.context)
        ms.done(h, detail=f"operatorCRDs={survey.airflow_crd_count} airflowCRs={len(survey.airflow_crs)}")

        if args.survey_only:
            ms.print_summary_table()
            _print("\n✅ Survey complete (--survey-only).")
            return 0

        # Step: Docker network (CP must share the operator cluster's network).
        h = ms.start(f"Ensure Docker network `{settings.docker_network}` exists")
        _ensure_docker_network(settings.docker_network)
        if settings.docker_network not in _container_networks(dp_node_container):
            _print(
                f"  ⚠️  Operator node {dp_node_container} is not on `{settings.docker_network}`. "
                "CP↔DP gRPC over the Docker network may fail; pass --docker-network to match."
            )
        ms.done(h)

        # Step: local pull-through registry proxies.
        registry_config: Path | None = None
        if not args.no_local_registry:
            h = ms.start("Ensure local pull-through registry proxy containers are running")
            _ensure_local_registries(settings.docker_network)
            registry_config = _get_registry_config_path(settings.docker_network)
            ms.done(h, detail=f"config={registry_config}")
        else:
            ms.skip("Local registry proxy setup", reason="--no-local-registry set")

        # Step: TLS + mkcert root CA.
        if not args.skip_certs:
            h = ms.start("Generate TLS certs (mkcert) with CP+DP SANs")
            cert_path, key_path, mkcert_root_ca = _ensure_tls_certs(settings)
            ms.done(h, detail=f"cert={cert_path}")
        else:
            ms.skip("Generate TLS certs (mkcert)", reason="--skip-certs set")
            mkcert_root_ca = _mkcert_caroot(_mkcert_path())
            cert_dir = HELPER_DIR / "certs"
            cert_path = cert_dir / "astronomer-tls.pem"
            key_path = cert_dir / "astronomer-tls.key"

        # Step: create the fresh control-plane k3d cluster.
        cp_context = f"k3d-{cp.cluster_name}"
        if not args.skip_cp:
            h = ms.start(f"Ensure control-plane k3d cluster exists ({cp.cluster_name})")
            if args.recreate_cp_cluster:
                _delete_k3d_cluster(cp.cluster_name)
            if not _k3d_cluster_exists(cp.cluster_name):
                # The serverlb must proxy 80/443 for container-IP ingress access, so we always map
                # them. But the operator cluster already publishes 8080/8443 on the host, so
                # auto-bump the HOST side to free ports to avoid Docker "port is already allocated".
                https_host = _pick_free_host_port(cp.https_port, avoid=set())
                http_host = _pick_free_host_port(cp.http_port, avoid={https_host})
                if (https_host, http_host) != (cp.https_port, cp.http_port):
                    _print(f"  CP host ports {cp.https_port}/{cp.http_port} taken; using {https_host}/{http_host}")
                _k3d_create_cluster(
                    name=cp.cluster_name,
                    docker_network=settings.docker_network,
                    ports=[f"{https_host}:443@loadbalancer", f"{http_host}:80@loadbalancer"],
                    mkcert_root_ca=mkcert_root_ca,
                    # Expand NodePort range so postgres can be exposed as NodePort 5432.
                    extra_k3s_args=["--kube-apiserver-arg=--service-node-port-range=1024-65535@server:0"],
                    registry_config=registry_config,
                )
            else:
                _debug(f"CP cluster already exists, skipping: {cp.cluster_name}")
            ms.done(h)
        else:
            ms.skip(f"Ensure control-plane k3d cluster exists ({cp.cluster_name})", reason="--skip-cp set")

        # Step: namespace + secrets in BOTH clusters (CP first if present, then the operator DP).
        h = ms.start(f"Apply namespace + secrets (ns={settings.namespace}) on CP + DP")
        target_contexts = ([] if args.skip_cp else [cp_context]) + ([] if args.skip_dp else [dp.context])
        for ctx in target_contexts:
            _kubectl_create_namespace(ctx, settings.namespace)
            _kubectl_apply_tls_secret(
                context=ctx, namespace=settings.namespace,
                secret_name=settings.tls_secret_name, cert_path=cert_path, key_path=key_path,
            )
            _kubectl_apply_generic_secret_from_file(
                context=ctx, namespace=settings.namespace,
                secret_name=settings.mkcert_root_ca_secret_name,
                key=settings.mkcert_root_ca_secret_key, file_path=mkcert_root_ca,
            )
        ms.done(h, detail=f"tlsSecret={settings.tls_secret_name} caSecret={settings.mkcert_root_ca_secret_name}")

        # Step: values files.
        h = ms.start("Write CP/DP Helm values files")
        values_dir = Path(args.values_dir) if args.values_dir else Path(tempfile.mkdtemp(prefix="astro-op-dp-"))
        values_dir.mkdir(parents=True, exist_ok=True)
        cp_values_path = values_dir / "cp-values.yaml"
        dp_values_path = values_dir / "dp-values.yaml"
        _write_values_file(cp_values_path, _cp_values_yaml(settings))
        _write_values_file(dp_values_path, _operator_dp_values_yaml(settings, survey))
        ms.done(h, detail=f"dir={values_dir}")

        if args.helm_deps_update:
            h = ms.start("Helm dependency update")
            _helm_dependency_update(REPO_ROOT)
            ms.done(h)
        else:
            ms.skip("Helm dependency update", reason="Disabled by default (vendored local charts)")

        extra_values = [Path(f) for f in args.helm_values]

        # Step: install the control plane.
        if not args.skip_cp:
            h = ms.start(f"Helm install/upgrade Control Plane (context={cp_context})")
            _helm_upgrade_install(
                context=cp_context, chart_dir=REPO_ROOT, release_name=settings.release_name,
                namespace=settings.namespace, values_file=cp_values_path,
                extra_values_files=extra_values, timeout=settings.helm_timeout, debug=settings.helm_debug,
            )
            # No --wait above (would deadlock on Prometheus pre-migration); wait on Deployments here,
            # by which point Helm has already run the post-install DB migration that creates the schema.
            _wait_for_deployments_available(cp_context, settings.namespace)
            ms.done(h)
        else:
            ms.skip("Helm install/upgrade Control Plane", reason="--skip-cp set")

        # Step: install the data plane onto the operator cluster.
        if not args.skip_dp:
            # astronomer-bootstrap on the DP points the platform DB at the CP's shared postgres.
            if not args.skip_cp:
                h = ms.start("Create DP astronomer-bootstrap secret (-> CP postgres)")
                cp_node_ip = _docker_inspect_ip(f"k3d-{cp.cluster_name}-server-0")
                _create_astronomer_bootstrap_secret_postgres(
                    context=dp.context, namespace=settings.namespace, pg_host=cp_node_ip,
                )
                ms.done(h, detail=f"pg_host={cp_node_ip}")

            # Patch the DP CoreDNS NodeHosts for CP ingress BEFORE the DP install (DP startup resolves CP).
            if not args.skip_dns_reconcile and not args.skip_cp:
                h = ms.start(f"Pre-DP: reconcile {dp.cluster_name} CoreDNS NodeHosts for CP ingress")
                _run_dns_reconcile(settings)
                ms.done(h)

            h = ms.start(f"Helm install/upgrade Data Plane onto operator cluster (context={dp.context})")
            _helm_upgrade_install(
                context=dp.context, chart_dir=REPO_ROOT, release_name=settings.release_name,
                namespace=settings.namespace, values_file=dp_values_path,
                extra_values_files=extra_values, timeout=settings.helm_timeout, debug=settings.helm_debug,
            )
            _wait_for_deployments_available(dp.context, settings.namespace)
            ms.done(h)
        else:
            ms.skip("Helm install/upgrade Data Plane", reason="--skip-dp set")

        # Step: final DNS reconcile + DP node houston pin.
        if not args.skip_dns_reconcile and not args.skip_cp and not args.skip_dp:
            h = ms.start("Reconcile cross-cluster DNS + node-level hosts pins")
            _run_dns_reconcile(settings)
            _ensure_dp_node_houston_hosts_pin(settings)
            ms.done(h)
        else:
            ms.skip("Reconcile cross-cluster DNS + node-level hosts pins", reason="skipped (--skip-* set)")

        # Step: verify the operator's Airflow CRs are undisturbed.
        h = ms.start("Verify operator Airflow CRs untouched (before/after snapshot)")
        crs_after = _snapshot_airflow_crs(dp.context)
        if crs_before == crs_after:
            ms.done(h, detail="identical")
        else:
            ms.fail(h, error="Airflow CR snapshot changed during install — investigate before proceeding!")
            _print("\n  BEFORE:\n" + (crs_before or "  <none>"))
            _print("\n  AFTER:\n" + (crs_after or "  <none>"))

        ms.print_summary_table()
        _print_host_etc_hosts_instructions(settings)
        _print_registration_runbook(settings)
        _print("\n✅ Completed. The control plane is up and the operator cluster now runs the APC data plane.")
        _print("   Next: run the registration step above, then proceed to M2 / Task 2 (connect Commander to the CRs).")
        return 0
    except Exception as e:  # noqa: BLE001
        ms.fail_active_if_any(error=str(e))
        ms.print_summary_table()
        _print(f"\n❌ Failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
