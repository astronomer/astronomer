#!/usr/bin/env python3
"""
One-shot standalone Airflow operator setup.

Automates the workflow documented in
  astronomer/docs/operator/operator-inheritance/examples/README.md

Steps:
  1.  Validate prerequisites (docker/k3d/kubectl/helm; k3d only required when --cluster-name is set)
  2.  Ensure Docker network                            (k3d mode only)
  3.  Ensure local pull-through registry proxies       (k3d mode, skippable)
  4.  Create k3d cluster                               (k3d mode only)
  5.  Create deployment namespace
  6.  Install cert-manager (required for operator admission webhooks)
  7.  Install airflow-operator Helm chart
  8.  Optionally install KEDA (CeleryWorker autoscaling)
  9.  Create Secrets referenced by the Airflow CR
  10. Create KubernetesExecutor pod template ConfigMap  (optional)
  11. Apply the Airflow CR
  12. Print access instructions (port-forward commands)

All steps are idempotent — safe to re-run.

Generated secrets (fernet key, webserver secret key, redis password) are persisted to
  ~/.local/share/astronomer-software/operator-standalone/<namespace>-secrets.json
so re-runs do not rotate keys and break existing deployments.

Examples
--------
# Zero-config local dev cluster (k3d + in-cluster postgres + LocalExecutor):
  python3 bin/setup-operator-standalone.py --cluster-name airflow-dev --in-cluster-postgres

# Full local cluster with external postgres + KEDA:
  python3 bin/setup-operator-standalone.py \\
    --cluster-name airflow-local \\
    --metadata-db-url 'postgresql+psycopg2://airflow:pw@host.docker.internal:5432/airflow' \\
    --install-keda

# Prerequisites only on an existing cluster (no k3d, no CR apply):
  python3 bin/setup-operator-standalone.py \\
    --context my-cluster \\
    --metadata-db-url 'postgresql+psycopg2://airflow:pw@db.example.com:5432/airflow' \\
    --no-apply-cr
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HELPER_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "operator-standalone"
REGISTRY_CONFIG_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "registry-configs"
K3D_REGISTRY_CONFIG_PATH = Path.home() / ".local" / "share" / "astronomer-software" / "k3d-registry.yaml"
REGISTRY_IMAGE = "registry:2"

CERT_MANAGER_VERSION = "v1.19.4"
CERT_MANAGER_MANIFEST_URL = (
    f"https://github.com/cert-manager/cert-manager/releases/download/{CERT_MANAGER_VERSION}/cert-manager.yaml"
)

# The airflow-operator's apiserver controller watches monitoring.coreos.com/v1 ServiceMonitor
# (an optional Prometheus Operator type). Without the CRD the controller's cache fails to sync.
# We install just the ServiceMonitor CRD (not the full Prometheus Operator) so the watch succeeds.
PROMETHEUS_OPERATOR_VERSION = "v0.76.0"
SERVICE_MONITOR_CRD_URL = (
    f"https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/{PROMETHEUS_OPERATOR_VERSION}"
    "/example/prometheus-operator-crd/monitoring.coreos.com_servicemonitors.yaml"
)

OPERATOR_HELM_REPO_NAME = "astronomer"
OPERATOR_HELM_REPO_URL = "https://helm.astronomer.io"
OPERATOR_CHART_NAME = "airflow-operator"
# Relative path from the repo root to the local operator Helm chart.
# When present, the local chart is preferred over the remote repo so that CRDs and
# RBAC stay in sync with whatever operator image is configured in values.yaml.
LOCAL_OPERATOR_CHART_REL = Path("airflow-operator") / "helm"

KEDA_HELM_REPO_NAME = "kedacore"
KEDA_HELM_REPO_URL = "https://kedacore.github.io/charts"
KEDA_CHART_NAME = "keda"

DEFAULT_AIRFLOW_IMAGE = "quay.io/astronomer/astro-runtime"
DEFAULT_AIRFLOW_VERSION = "13.7.0"


# ---------------------------------------------------------------------------
# Local pull-through registry helpers
# (Mirrors setup-cp-dp-k3d.py — see bin/setup-local-registry.py for standalone management.)
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
    REGISTRY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for spec in _REGISTRY_SPECS:
        config_path = REGISTRY_CONFIG_DIR / f"{spec.name}.yml"
        config_path.write_text(_registry_docker_config(spec))
        _ensure_registry(spec, docker_network)


def _get_registry_config_path() -> Path:
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
    K3D_REGISTRY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    K3D_REGISTRY_CONFIG_PATH.write_text(content)
    return K3D_REGISTRY_CONFIG_PATH


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    context: str
    namespace: str
    release_prefix: str
    operator_namespace: str
    operator_release: str
    keda_namespace: str
    # k3d cluster creation
    cluster_name: str          # empty string = skip cluster creation
    docker_network: str
    https_port: int
    http_port: int
    agents: int
    recreate_cluster: bool
    no_local_registry: bool
    # database
    metadata_db_url: str
    result_backend_url: str
    db_ca_cert: Path | None
    in_cluster_postgres: bool
    reset_postgres: bool
    # optional integrations
    elasticsearch_url: str
    install_keda: bool
    install_operator: bool
    install_service_monitor_crd: bool
    operator_chart_version: str
    operator_chart_path: str   # explicit local chart dir; empty = auto-detect, then remote
    # image registry
    registry_server: str
    registry_username: str
    registry_password: str
    registry_email: str
    # airflow
    airflow_image: str
    airflow_version: str
    executor: str
    # CR
    apply_cr: bool
    cr_path: str               # empty = generate CR from settings
    pod_template_path: Path | None
    # admin user (Airflow 2 / FAB auth)
    create_admin_user: bool
    admin_username: str
    admin_password: str
    admin_email: str


# ---------------------------------------------------------------------------
# Printing / logging helpers
# ---------------------------------------------------------------------------


def _print(msg: str) -> None:
    print(msg, flush=True)


def _debug_enabled() -> bool:
    return os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"}


def _debug(msg: str) -> None:
    if _debug_enabled():
        _print(f"DEBUG: {msg}")


# ---------------------------------------------------------------------------
# Milestone tracker
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

        def _truncate(s: str, n: int) -> str:
            return s if len(s) <= n else (f"{s[:n-3]}..." if n > 3 else s[:n])

        rows: list[list[str]] = []
        for row in self._rows:
            status_cell = {
                "success": "✅ Success",
                "failure": "❌ Failed",
                "skipped": "⏭️  Skipped",
                "running": "⏳ Running",
            }.get(str(row["status"]), str(row["status"]))

            duration_s = row.get("duration_s")
            duration_cell = f"{duration_s:.1f}s" if isinstance(duration_s, (int, float)) else "-"

            detail = _one_line(str(row.get("detail") or ""))
            error = _one_line(str(row.get("error") or ""))
            details_cell = (f"{detail} " if detail else "") + error if error else detail

            rows.append([
                str(int(row["idx"])),
                _truncate(_one_line(str(row["title"])), 70),
                status_cell,
                duration_cell,
                _truncate(details_cell, 90),
            ])

        headers = ["#", "Milestone", "Status", "Duration", "Details"]
        widths = [len(h) for h in headers]
        for r in rows:
            for i, cell in enumerate(r):
                widths[i] = max(widths[i], len(cell))

        sep = lambda c="-": "+" + "+".join(c * (w + 2) for w in widths) + "+"  # noqa: E731
        fmt = lambda cells: "|" + "|".join(f" {cells[i].ljust(widths[i])} " for i in range(len(cells))) + "|"  # noqa: E731

        _print("\nMilestones summary:\n")
        _print(sep())
        _print(fmt(headers))
        _print(sep())
        for r in rows:
            _print(fmt(r))
        _print(sep())

    def _row(self, h: MilestoneHandle) -> dict[str, object]:
        for row in reversed(self._rows):
            if int(row["idx"]) == h.idx:
                return row
        raise RuntimeError(f"Milestone handle not found: {h.idx}")


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------


class CommandError(RuntimeError):
    pass


def _run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
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
        raise CommandError(f"Command failed ({proc.returncode}): {shlex.join(cmd)}\n{(proc.stderr or '').strip()}")
    return proc


def _which(exe: str) -> str | None:
    proc = _run(["/usr/bin/env", "bash", "-lc", f"command -v {shlex.quote(exe)}"], check=False)
    return (proc.stdout or "").strip() or None


def _require_executable(exe: str, *, hint: str) -> None:
    if _which(exe) is None:
        raise RuntimeError(f"Missing required executable `{exe}`. {hint}")


# ---------------------------------------------------------------------------
# Docker / k3d cluster helpers
# ---------------------------------------------------------------------------


def _docker_network_exists(name: str) -> bool:
    return _run(["docker", "network", "inspect", name], check=False).returncode == 0


def _ensure_docker_network(name: str) -> None:
    if not _docker_network_exists(name):
        _print(f"  Creating Docker network: {name}")
        _run(["docker", "network", "create", name])


def _k3d_cluster_exists(name: str) -> bool:
    return _run(["k3d", "cluster", "get", name], check=False).returncode == 0


def _delete_k3d_cluster(name: str) -> None:
    if _k3d_cluster_exists(name):
        _print(f"  Deleting k3d cluster: {name}")
        _run(["k3d", "cluster", "delete", name])


def _k3d_create_cluster(
    *,
    name: str,
    docker_network: str,
    https_port: int,
    http_port: int,
    agents: int,
    registry_config: Path | None,
) -> None:
    cmd = [
        "k3d", "cluster", "create", name,
        "--network", docker_network,
        "--agents", str(agents),
        "--k3s-arg", "--disable=traefik@server:0",
        "--port", f"{https_port}:443@loadbalancer",
        "--port", f"{http_port}:80@loadbalancer",
    ]
    if registry_config is not None:
        cmd.extend(["--registry-config", str(registry_config)])
    _print(f"  Creating k3d cluster: {name}")
    _run(cmd, capture=False)


def _docker_inspect_ip(container: str) -> str:
    proc = _run(
        ["docker", "inspect", container, "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
        check=True,
    )
    ip = proc.stdout.strip()
    if not ip:
        raise RuntimeError(f"Could not determine IP for container {container}")
    return ip


# ---------------------------------------------------------------------------
# State file — persists generated secret values across re-runs
# ---------------------------------------------------------------------------


def _state_path(namespace: str) -> Path:
    HELPER_DIR.mkdir(parents=True, exist_ok=True)
    return HELPER_DIR / f"{namespace}-secrets.json"


def _load_state(namespace: str) -> dict[str, str]:
    p = _state_path(namespace)
    return json.loads(p.read_text()) if p.exists() else {}


def _save_state(namespace: str, state: dict[str, str]) -> None:
    _state_path(namespace).write_text(json.dumps(state, indent=2))


def _get_or_generate(state: dict[str, str], key: str, generator: "Callable[[], str]") -> str:  # type: ignore[name-defined]
    if key not in state:
        state[key] = generator()
    return state[key]


# ---------------------------------------------------------------------------
# Secret value generators
# ---------------------------------------------------------------------------


def _generate_fernet_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def _generate_secret_key(n: int = 32) -> str:
    return base64.b64encode(secrets.token_bytes(n)).decode()


def _generate_password(n: int = 24) -> str:
    return base64.b64encode(secrets.token_bytes(n)).decode()


# ---------------------------------------------------------------------------
# kubectl helpers
# ---------------------------------------------------------------------------


def _kubectl_apply_yaml(context: str, yaml_text: str) -> None:
    _run(["kubectl", "--context", context, "apply", "-f", "-"], stdin=yaml_text)


def _resource_exists(context: str, namespace: str, kind: str, name: str) -> bool:
    proc = _run(
        ["kubectl", "--context", context, "-n", namespace, "get", kind, name],
        check=False,
    )
    return proc.returncode == 0


def _delete_resource(context: str, namespace: str, kind: str, name: str) -> bool:
    """Delete a namespaced resource if it exists. Returns True if a delete was issued."""
    if not _resource_exists(context, namespace, kind, name):
        return False
    _print(f"  Deleting {kind}/{name}")
    _run(
        ["kubectl", "--context", context, "-n", namespace, "delete", kind, name, "--wait=true"],
        check=False,
        capture=False,
    )
    return True


def _create_namespace(context: str, namespace: str) -> None:
    proc = _run(["kubectl", "--context", context, "create", "namespace", namespace], check=False)
    if proc.returncode != 0 and "AlreadyExists" not in (proc.stderr or ""):
        raise CommandError(f"Failed to create namespace {namespace}: {(proc.stderr or '').strip()}")


def _apply_literal_secret(*, context: str, namespace: str, name: str, literals: dict[str, str]) -> None:
    cmd = [
        "kubectl", "--context", context, "-n", namespace,
        "create", "secret", "generic", name,
        "--dry-run=client", "-o", "yaml",
    ]
    for k, v in literals.items():
        cmd.append(f"--from-literal={k}={v}")
    _kubectl_apply_yaml(context, _run(cmd).stdout)


def _apply_file_secret(*, context: str, namespace: str, name: str, key: str, file_path: Path) -> None:
    yaml_out = _run(
        [
            "kubectl", "--context", context, "-n", namespace,
            "create", "secret", "generic", name,
            f"--from-file={key}={file_path}",
            "--dry-run=client", "-o", "yaml",
        ]
    ).stdout
    _kubectl_apply_yaml(context, yaml_out)


def _apply_docker_registry_secret(
    *, context: str, namespace: str, name: str,
    server: str, username: str, password: str, email: str,
) -> None:
    yaml_out = _run(
        [
            "kubectl", "--context", context, "-n", namespace,
            "create", "secret", "docker-registry", name,
            f"--docker-server={server}",
            f"--docker-username={username}",
            f"--docker-password={password}",
            f"--docker-email={email}",
            "--dry-run=client", "-o", "yaml",
        ]
    ).stdout
    _kubectl_apply_yaml(context, yaml_out)


def _apply_configmap_from_file(
    *, context: str, namespace: str, name: str, key: str, file_path: Path,
) -> None:
    yaml_out = _run(
        [
            "kubectl", "--context", context, "-n", namespace,
            "create", "configmap", name,
            f"--from-file={key}={file_path}",
            "--dry-run=client", "-o", "yaml",
        ]
    ).stdout
    _kubectl_apply_yaml(context, yaml_out)


# ---------------------------------------------------------------------------
# cert-manager
# ---------------------------------------------------------------------------


def _install_cert_manager(context: str) -> None:
    _print(f"  Applying cert-manager {CERT_MANAGER_VERSION}")
    _run(["kubectl", "--context", context, "apply", "-f", CERT_MANAGER_MANIFEST_URL], capture=False)


def _pin_cert_manager_to_control_plane(context: str) -> None:
    patch = '{"spec":{"template":{"spec":{"nodeSelector":{"node-role.kubernetes.io/control-plane":"true"}}}}}'
    for deployment in ("cert-manager-webhook", "cert-manager-cainjector", "cert-manager"):
        _run(
            [
                "kubectl", "--context", context,
                "patch", "deployment", deployment,
                "-n", "cert-manager",
                "--type=merge", f"--patch={patch}",
            ],
            check=False,
        )


def _wait_for_cert_manager(context: str, timeout_s: int = 180) -> None:
    _print(f"  Waiting for cert-manager to become ready ({context})")
    for deployment in ("cert-manager", "cert-manager-webhook"):
        _run(
            [
                "kubectl", "--context", context,
                "-n", "cert-manager",
                "wait", "--for=condition=available",
                f"deployment/{deployment}",
                f"--timeout={timeout_s}s",
            ],
            capture=False,
        )


# ---------------------------------------------------------------------------
# Prometheus Operator ServiceMonitor CRD
# ---------------------------------------------------------------------------


def _install_service_monitor_crd(context: str) -> None:
    """Server-side apply just the ServiceMonitor CRD so the operator's apiserver watch can sync."""
    _print(f"  Applying ServiceMonitor CRD ({PROMETHEUS_OPERATOR_VERSION})")
    _run(
        ["kubectl", "--context", context, "apply", "--server-side", "-f", SERVICE_MONITOR_CRD_URL],
        capture=False,
    )


# ---------------------------------------------------------------------------
# Helm helpers
# ---------------------------------------------------------------------------


def _find_local_operator_chart(explicit_path: str = "") -> Path | None:
    """Return the local airflow-operator Helm chart path, or None to fall back to the remote chart.

    Resolution order:
      1. ``explicit_path`` (from --operator-chart-path), validated to contain a Chart.yaml.
      2. Auto-detect: walk up from this script and return the first
         ``<parent>/airflow-operator/helm`` containing a Chart.yaml.

    Detection is intentionally NOT gated on a ``.git`` directory. In a monorepo-style checkout
    the chart lives in a sibling repo (e.g. ``…/astro_coding_e2e/airflow-operator/helm``) whose
    parent dir is not itself a git root, so a ``.git``-gated walk silently misses it and the
    caller falls back to the remote chart — whose RBAC/CRDs can lag the operator image and cause
    'forbidden' / 'no matches for kind' errors at runtime. Using the in-repo chart keeps RBAC,
    CRDs and the operator image in lockstep.
    """
    if explicit_path:
        cand = Path(explicit_path).expanduser().resolve()
        if cand.is_dir() and (cand / "Chart.yaml").exists():
            return cand
        raise RuntimeError(f"--operator-chart-path '{explicit_path}' is not a Helm chart directory (no Chart.yaml)")
    for parent in Path(__file__).resolve().parents:
        candidate = parent / LOCAL_OPERATOR_CHART_REL
        if candidate.is_dir() and (candidate / "Chart.yaml").exists():
            return candidate
    return None


def _helm_repo_add(name: str, url: str) -> None:
    _run(["helm", "repo", "add", "--force-update", name, url])
    _run(["helm", "repo", "update", name])


def _helm_upgrade_install(
    *,
    context: str,
    release: str,
    chart: str,
    namespace: str,
    create_namespace: bool = True,
    version: str = "",
    extra_set: list[str] | None = None,
    timeout: str = "5m",
) -> None:
    cmd = [
        "helm", "upgrade", "--install", release, chart,
        "--kube-context", context,
        "--namespace", namespace,
        "--wait", "--timeout", timeout,
    ]
    if create_namespace:
        cmd.append("--create-namespace")
    if version:
        cmd.extend(["--version", version])
    for s in extra_set or []:
        cmd.extend(["--set", s])
    _print(f"  helm upgrade --install {release} {chart} -n {namespace}")
    _run(cmd, capture=False)


# ---------------------------------------------------------------------------
# Secrets setup
# ---------------------------------------------------------------------------


def _setup_secrets(settings: Settings, state: dict[str, str]) -> None:
    ctx = settings.context
    ns = settings.namespace
    p = settings.release_prefix

    fernet_key = _get_or_generate(state, "fernet_key", _generate_fernet_key)
    webserver_secret = _get_or_generate(state, "webserver_secret_key", _generate_secret_key)
    redis_password = _get_or_generate(state, "redis_password", _generate_password)

    _apply_literal_secret(context=ctx, namespace=ns, name=f"{p}-fernet-key",
                          literals={"fernet-key": fernet_key})
    _apply_literal_secret(context=ctx, namespace=ns, name=f"{p}-webserver-secret-key",
                          literals={"webserver-secret-key": webserver_secret})

    if not settings.in_cluster_postgres:
        _apply_literal_secret(context=ctx, namespace=ns, name=f"{p}-metadata",
                              literals={"connection": settings.metadata_db_url})
        _apply_literal_secret(context=ctx, namespace=ns, name=f"{p}-result-backend",
                              literals={"connection": settings.result_backend_url})
        pgbouncer_conn = settings.metadata_db_url.replace("postgresql+psycopg2://", "postgresql://")
        _apply_literal_secret(context=ctx, namespace=ns, name=f"{p}-pgbouncer-connection",
                              literals={"connection": pgbouncer_conn})

    if settings.executor == "CeleryExecutor":
        redis_conn = f"redis://:{redis_password}@{p}-redis:6379/0"
        _apply_literal_secret(context=ctx, namespace=ns, name=f"{p}-redis-password",
                              literals={"password": redis_password})
        _apply_literal_secret(context=ctx, namespace=ns, name=f"{p}-redis-connection",
                              literals={"connection": redis_conn})

    if settings.db_ca_cert is not None:
        _apply_file_secret(context=ctx, namespace=ns, name=f"{p}-db-ca",
                           key="ca.crt", file_path=settings.db_ca_cert)

    if settings.elasticsearch_url:
        _apply_literal_secret(context=ctx, namespace=ns, name=f"{p}-elasticsearch",
                              literals={"connection": settings.elasticsearch_url})

    if settings.registry_username and settings.registry_password:
        _apply_docker_registry_secret(
            context=ctx, namespace=ns, name=f"{p}-registry",
            server=settings.registry_server,
            username=settings.registry_username,
            password=settings.registry_password,
            email=settings.registry_email or f"{settings.registry_username}@example.com",
        )


# ---------------------------------------------------------------------------
# In-cluster postgres cleanup
# ---------------------------------------------------------------------------


def _postgres_resource_names(release_prefix: str) -> dict[str, str]:
    """Names of the in-cluster postgres resources managed by the operator."""
    pg = f"{release_prefix}-postgres"
    return {
        # StatefulSet VolumeClaimTemplate PVC: <volume>-<statefulset>-<ordinal>
        "pvc": f"data-{pg}-0",
        "password_secret": f"{pg}-password",
        "metadata_secret": f"{pg}-metadata",
        "result_backend_secret": f"{pg}-result-backend",
    }


def _cleanup_stale_postgres_pvc(settings: Settings) -> str:
    """
    Prevent the in-cluster-postgres password-mismatch loop.

    The operator runs postgres as a StatefulSet whose PVC (`data-<release>-postgres-0`) is
    NEVER auto-deleted. The postgres password is generated once and stored in a secret owned
    by the Postgres CR — so deleting the Airflow CR garbage-collects the password secret while
    the PVC survives. On the next run the operator generates a NEW password, but the bitnami
    image ignores POSTGRES_PASSWORD when the data dir is already initialised, so postgres keeps
    the OLD password and every connection fails with "password authentication failed".

    Heuristic (safe auto-heal): if the password secret is absent but the PVC exists, they are
    guaranteed mismatched, so the PVC is stale and we delete it. With --reset-postgres we always
    delete the PVC + owned secrets for a guaranteed-fresh database.

    Returns a short status string for the milestone detail (or "" when nothing was done).
    """
    if not settings.in_cluster_postgres:
        return ""

    ctx, ns = settings.context, settings.namespace
    names = _postgres_resource_names(settings.release_prefix)
    pvc_exists = _resource_exists(ctx, ns, "pvc", names["pvc"])
    pwd_exists = _resource_exists(ctx, ns, "secret", names["password_secret"])

    if settings.reset_postgres:
        if not (pvc_exists or pwd_exists):
            return "no existing postgres state"
        _print("  --reset-postgres: removing in-cluster postgres PVC + owned secrets")
        _delete_resource(ctx, ns, "pvc", names["pvc"])
        for key in ("password_secret", "metadata_secret", "result_backend_secret"):
            _delete_resource(ctx, ns, "secret", names[key])
        return f"reset postgres (deleted pvc {names['pvc']})"

    # Auto-heal: stale PVC left behind by a previous CR deletion.
    if pvc_exists and not pwd_exists:
        _print(
            f"  Detected stale postgres PVC ({names['pvc']}) without its password secret — "
            "deleting so postgres reinitialises with the regenerated password"
        )
        _delete_resource(ctx, ns, "pvc", names["pvc"])
        # Drop any orphaned connection secrets too so they regenerate in lockstep.
        for key in ("metadata_secret", "result_backend_secret"):
            _delete_resource(ctx, ns, "secret", names[key])
        return f"healed stale pvc {names['pvc']}"

    return "postgres state consistent"


# ---------------------------------------------------------------------------
# Airflow admin user (Airflow 2 / FAB auth)
# ---------------------------------------------------------------------------


def _wait_for_deployment_available(context: str, namespace: str, name: str, timeout_s: int = 300) -> None:
    """Wait for a Deployment to be created by the operator, then for it to become available."""
    # The operator creates the deployment asynchronously after the CR is applied, so first
    # poll for its existence (kubectl wait errors immediately on a missing object).
    for _ in range(60):  # ~2 min at 2s intervals
        if _resource_exists(context, namespace, "deployment", name):
            break
        time.sleep(2)
    else:
        raise CommandError(f"Deployment {name} was not created within the expected time")
    _run(
        [
            "kubectl", "--context", context, "-n", namespace,
            "wait", "--for=condition=available",
            f"deployment/{name}", f"--timeout={timeout_s}s",
        ],
        capture=False,
    )


def _create_admin_user(settings: Settings) -> str:
    """
    Create a FAB admin user in the webserver pod (Airflow 2 auth).

    The standalone operator (no Houston) ships an empty FAB user table, so a user must be
    created before anyone can log in. Idempotent: a pre-existing user is treated as success.
    """
    ctx, ns = settings.context, settings.namespace
    deploy = f"{settings.release_prefix}-webserver"

    _print(f"  Waiting for {deploy} to be ready")
    _wait_for_deployment_available(ctx, ns, deploy)

    _print(f"  Creating admin user '{settings.admin_username}'")
    proc = _run(
        [
            "kubectl", "--context", ctx, "-n", ns,
            "exec", f"deployment/{deploy}", "--",
            "airflow", "users", "create",
            "--username", settings.admin_username,
            "--password", settings.admin_password,
            "--firstname", "Admin",
            "--lastname", "User",
            "--role", "Admin",
            "--email", settings.admin_email,
        ],
        check=False,
    )
    combined = ((proc.stdout or "") + (proc.stderr or "")).lower()
    if proc.returncode == 0:
        return f"user={settings.admin_username}"
    if "already exist" in combined:
        return f"user={settings.admin_username} (already existed)"
    raise CommandError(f"Failed to create admin user: {((proc.stderr or proc.stdout) or '').strip()}")


# ---------------------------------------------------------------------------
# Airflow CR generation
# ---------------------------------------------------------------------------


def _generate_cr_yaml(settings: Settings) -> str:
    """
    Generate a minimal Airflow CR based on the current settings.

    Used when --cr-path is not given. This is simpler than the reference
    production-airflow.yaml but covers all the secrets we create and produces
    a working deployment out of the box.
    """
    p = settings.release_prefix
    image = f"{settings.airflow_image}:{settings.airflow_version}"
    executor = settings.executor

    secrets_block = f"""\
  secrets:
    fernetKeySecretName: {p}-fernet-key
    webserverSecretKeySecretName: {p}-webserver-secret-key
"""
    if not settings.in_cluster_postgres:
        secrets_block += f"""\
    metadataSecretName: {p}-metadata
    resultBackendSecretName: {p}-result-backend
    pgbouncerConnectionSecretName: {p}-pgbouncer-connection
"""
    if executor == "CeleryExecutor":
        secrets_block += f"""\
    redisConnectionSecretName: {p}-redis-connection
    redisPasswordSecretName: {p}-redis-password
"""

    image_pull_secret_block = (
        f"  imagePullSecret: {p}-registry\n" if settings.registry_username else ""
    )

    db_ssl_block = ""
    if settings.db_ca_cert is not None:
        db_ssl_block = f"""\
  databaseSSLMode: verify-full
  databaseSSLSecretName: {p}-db-ca
"""

    use_ext_fernet = "  useExternallyManagedFernetKey: true\n" if not settings.in_cluster_postgres else ""

    es_env_block = ""
    if settings.elasticsearch_url:
        es_env_block = f"""\
  env:
    - name: AIRFLOW__LOGGING__REMOTE_LOGGING
      value: "True"
    - name: AIRFLOW__ELASTICSEARCH__HOST
      valueFrom:
        secretKeyRef:
          name: {p}-elasticsearch
          key: connection
    - name: AIRFLOW__ELASTICSEARCH__JSON_FORMAT
      value: "True"
"""

    pod_template_block = ""
    if settings.pod_template_path is not None:
        pod_template_block = f"  podTemplateConfigMapName: {p}-kexec-pod-template\n"

    # The webhook defaults pgbouncer.enabled=true when the field is absent.
    # With in-cluster postgres, createPgBouncerConnectionSecrets (step 18 in the
    # reconcile chain) reads the metadata secret before postgres is ready, returns
    # ErrorResult, and the loop never reaches SA creation (step 26).
    # Explicitly disabling pgbouncer avoids that dependency entirely for dev clusters.
    pgbouncer_block = "  pgbouncer:\n    enabled: false\n" if settings.in_cluster_postgres else ""

    return f"""\
apiVersion: airflow.apache.org/v1beta1
kind: Airflow
metadata:
  name: {p}
  namespace: {settings.namespace}
spec:
  executor: {executor}
  image: {image}
{image_pull_secret_block}\
  runtimeVersion: "{settings.airflow_version}"
  inClusterPostgres: {"true" if settings.in_cluster_postgres else "false"}
  enableNetworkPolicies: false
{use_ext_fernet}\
{db_ssl_block}\
{pgbouncer_block}\
{secrets_block}\
{es_env_block}\
{pod_template_block}\
  scheduler:
    replicas: 1

  webserver:
    replicas: 1

  triggerer:
    replicas: 1
"""


# ---------------------------------------------------------------------------
# Prerequisite validation
# ---------------------------------------------------------------------------


def _validate_prereqs(need_k3d: bool) -> None:
    _require_executable("kubectl", hint="Install kubectl and ensure it is in PATH.")
    _require_executable("helm", hint="Install helm and ensure it is in PATH.")
    if need_k3d:
        _require_executable("docker", hint="Install Docker Desktop or OrbStack and ensure `docker` works.")
        _require_executable("k3d", hint="Install k3d (e.g. `brew install k3d` on macOS).")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "One-shot standalone Airflow operator setup — creates a k3d cluster, "
            "installs the operator, wires up all prerequisites, and applies an Airflow CR."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Zero-config local dev (k3d cluster + in-cluster postgres + LocalExecutor):
  python3 bin/setup-operator-standalone.py --cluster-name airflow-dev --in-cluster-postgres

  # Full local cluster with external postgres + KEDA + CeleryExecutor:
  python3 bin/setup-operator-standalone.py \\
    --cluster-name airflow-local \\
    --metadata-db-url 'postgresql+psycopg2://airflow:pw@host.docker.internal:5432/airflow' \\
    --executor CeleryExecutor --install-keda

  # Existing cluster, prerequisites only (no CR apply):
  python3 bin/setup-operator-standalone.py \\
    --context my-cluster \\
    --metadata-db-url 'postgresql+psycopg2://airflow:pw@db.example.com:5432/airflow' \\
    --no-apply-cr

  # Use a custom CR file instead of the generated one:
  python3 bin/setup-operator-standalone.py \\
    --cluster-name airflow-dev --in-cluster-postgres \\
    --cr-path astronomer/docs/operator/operator-inheritance/examples/production-airflow.yaml
""",
    )

    # --- k3d cluster ---
    cluster_group = parser.add_argument_group("k3d cluster (skipped when --context is given without --cluster-name)")
    cluster_group.add_argument(
        "--cluster-name",
        default="",
        help="Create a k3d cluster with this name and use it. Mutually exclusive with --context.",
    )
    cluster_group.add_argument("--docker-network", default="airflow-standalone-net",
                               help="Docker network for k3d. Default: %(default)s")
    cluster_group.add_argument("--https-port", type=int, default=8443,
                               help="Host HTTPS port mapped to the cluster LoadBalancer. Default: %(default)s")
    cluster_group.add_argument("--http-port", type=int, default=8080,
                               help="Host HTTP port mapped to the cluster LoadBalancer. Default: %(default)s")
    cluster_group.add_argument(
        "--num-agents", type=int, default=0,
        help="Number of k3d agent (worker) nodes. Default: %(default)s",
    )
    cluster_group.add_argument("--recreate-cluster", action="store_true",
                               help="Delete and recreate the k3d cluster if it already exists.")
    cluster_group.add_argument(
        "--no-local-registry", action="store_true",
        help="Skip pull-through registry proxy setup (images pulled directly from remote).",
    )

    # --- existing cluster ---
    parser.add_argument(
        "--context", default="",
        help="kubectl context for an existing cluster. Ignored when --cluster-name is set.",
    )

    # --- namespace / naming ---
    parser.add_argument("--namespace", default="airflow-prod",
                        help="Deployment namespace for the Airflow CR. Default: %(default)s")
    parser.add_argument("--release-prefix", default="prod-airflow",
                        help="Prefix for K8s resource names (secrets, CR name). Default: %(default)s")

    # --- operator ---
    parser.add_argument("--operator-namespace", default="airflow-operator-system",
                        help="Namespace for the operator controller. Default: %(default)s")
    parser.add_argument("--operator-release", default="airflow-operator-system",
                        help="Helm release name for the operator. Default: %(default)s")
    parser.add_argument("--operator-chart-version", default="",
                        help="Helm chart version for the REMOTE airflow-operator chart. Ignored for a local chart.")
    parser.add_argument("--operator-chart-path", default="", metavar="DIR",
                        help="Path to the in-repo airflow-operator Helm chart. Overrides auto-detection "
                             "(which looks for a sibling airflow-operator/helm). Prefer this over the remote "
                             "chart so RBAC/CRDs match the operator image and avoid runtime 'forbidden' errors.")
    parser.add_argument("--no-install-operator", dest="install_operator", action="store_false",
                        help="Skip installing the airflow-operator Helm chart.")
    parser.set_defaults(install_operator=True)

    # --- cert-manager ---
    parser.add_argument("--skip-cert-manager", action="store_true",
                        help="Skip cert-manager install (if already present).")

    # --- ServiceMonitor CRD ---
    parser.add_argument(
        "--no-service-monitor-crd", dest="install_service_monitor_crd", action="store_false",
        help=(
            "Skip installing the Prometheus Operator ServiceMonitor CRD. The operator's apiserver "
            "controller watches ServiceMonitor; without the CRD its cache fails to sync. Pass this "
            "only if Prometheus Operator (or the CRD) is already installed."
        ),
    )
    parser.set_defaults(install_service_monitor_crd=True)

    # --- KEDA ---
    parser.add_argument("--install-keda", action="store_true",
                        help="Install KEDA (required for CeleryWorker autoscaling).")
    parser.add_argument("--keda-namespace", default="keda",
                        help="Namespace for KEDA. Default: %(default)s")

    # --- database ---
    db_group = parser.add_argument_group("database")
    db_group.add_argument(
        "--metadata-db-url", default="", metavar="URL",
        help=(
            "PostgreSQL metadata DB URL. "
            "Format: postgresql+psycopg2://user:pwd@host:5432/dbname. "
            "Required unless --in-cluster-postgres is set."
        ),
    )
    db_group.add_argument(
        "--result-backend-url", default="", metavar="URL",
        help="Celery result backend URL (db+postgresql://...). Derived from --metadata-db-url if omitted.",
    )
    db_group.add_argument("--db-ca-cert", default="", metavar="FILE",
                          help="Path to DB TLS CA cert PEM (for databaseSSLMode=verify-full).")
    db_group.add_argument(
        "--in-cluster-postgres", action="store_true",
        help="Use the operator's embedded postgres (dev only, NOT for production).",
    )
    db_group.add_argument(
        "--reset-postgres", action="store_true",
        help=(
            "Delete the in-cluster postgres PVC + owned secrets before applying the CR, forcing a "
            "fresh database. Use after deleting/re-applying the CR to clear a stale password volume. "
            "DESTRUCTIVE — wipes the metadata DB."
        ),
    )

    # --- optional integrations ---
    parser.add_argument("--elasticsearch-url", default="", metavar="URL",
                        help="Elasticsearch remote logging URL. Optional.")

    # --- registry ---
    reg_group = parser.add_argument_group("image registry")
    reg_group.add_argument("--registry-server", default="quay.io",
                           help="Docker registry server. Default: %(default)s")
    reg_group.add_argument("--registry-username", default="", help="Registry username.")
    reg_group.add_argument("--registry-password", default="", help="Registry password/token.")
    reg_group.add_argument("--registry-email", default="", help="Registry email.")

    # --- Airflow ---
    af_group = parser.add_argument_group("Airflow")
    af_group.add_argument("--airflow-image", default=DEFAULT_AIRFLOW_IMAGE,
                          help=f"Airflow image repository. Default: %(default)s")
    af_group.add_argument("--airflow-version", default=DEFAULT_AIRFLOW_VERSION,
                          help=f"Airflow / runtime image tag. Default: %(default)s")
    af_group.add_argument(
        "--executor", default="LocalExecutor",
        choices=["LocalExecutor", "CeleryExecutor", "KubernetesExecutor"],
        help="Airflow executor. Default: %(default)s",
    )

    # --- secrets ---
    parser.add_argument("--skip-secrets", action="store_true", help="Skip creating Secrets.")

    # --- pod template ---
    parser.add_argument("--pod-template-file", default="", metavar="FILE",
                        help="KubernetesExecutor pod_template_file.yaml to mount as a ConfigMap.")

    # --- CR ---
    cr_group = parser.add_argument_group("Airflow CR")
    cr_group.add_argument(
        "--no-apply-cr", dest="apply_cr", action="store_false",
        help="Skip applying the Airflow CR (prerequisites only).",
    )
    cr_group.add_argument(
        "--cr-path", default="", metavar="FILE",
        help=(
            "Path to a custom Airflow CR YAML to apply instead of the generated one. "
            "When omitted a CR is generated from the current settings."
        ),
    )
    parser.set_defaults(apply_cr=True)

    # --- admin user (Airflow 2 / FAB auth) ---
    user_group = parser.add_argument_group("admin user (Airflow 2 / FAB auth)")
    user_group.add_argument(
        "--create-admin-user", action="store_true",
        help=(
            "After the CR is applied, wait for the webserver and create a FAB admin user so you "
            "can log into the Airflow UI. Idempotent. Airflow 2 only (FAB auth)."
        ),
    )
    user_group.add_argument("--admin-username", default="admin", help="Admin username. Default: %(default)s")
    user_group.add_argument("--admin-password", default="admin", help="Admin password. Default: %(default)s")
    user_group.add_argument("--admin-email", default="admin@example.com",
                            help="Admin email. Default: %(default)s")

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:  # noqa: C901
    args = _parse_args()

    # --- validate conflicting flags ---
    if args.cluster_name and args.context:
        _print("❌ --cluster-name and --context are mutually exclusive.")
        return 1

    creating_cluster = bool(args.cluster_name)

    # --- resolve kubectl context ---
    if creating_cluster:
        context = f"k3d-{args.cluster_name}"
    elif args.context:
        context = args.context
    else:
        proc = _run(["kubectl", "config", "current-context"], check=False)
        if proc.returncode != 0:
            _print("❌ Could not determine current kubectl context. Pass --cluster-name or --context.")
            return 1
        context = proc.stdout.strip()
        _print(f"Using current kubectl context: {context}")

    # --- resolve DB URLs ---
    metadata_db_url = args.metadata_db_url
    result_backend_url = args.result_backend_url
    in_cluster_postgres = args.in_cluster_postgres
    if not in_cluster_postgres and not metadata_db_url:
        # No external DB provided — fall back to the operator's embedded postgres.
        in_cluster_postgres = True
        _print("No --metadata-db-url given; defaulting to --in-cluster-postgres (dev mode).")
    if not result_backend_url and metadata_db_url:
        result_backend_url = metadata_db_url.replace("postgresql+psycopg2://", "db+postgresql://")

    # --- executor validation ---
    executor = args.executor
    if in_cluster_postgres and executor == "CeleryExecutor":
        _print("⚠️  CeleryExecutor with in-cluster postgres is unusual. Continuing anyway.")

    settings = Settings(
        context=context,
        namespace=args.namespace,
        release_prefix=args.release_prefix,
        operator_namespace=args.operator_namespace,
        operator_release=args.operator_release,
        keda_namespace=args.keda_namespace,
        cluster_name=args.cluster_name,
        docker_network=args.docker_network,
        https_port=args.https_port,
        http_port=args.http_port,
        agents=args.num_agents,
        recreate_cluster=args.recreate_cluster,
        no_local_registry=args.no_local_registry,
        metadata_db_url=metadata_db_url,
        result_backend_url=result_backend_url,
        db_ca_cert=Path(args.db_ca_cert) if args.db_ca_cert else None,
        in_cluster_postgres=in_cluster_postgres,
        reset_postgres=args.reset_postgres,
        elasticsearch_url=args.elasticsearch_url,
        install_keda=args.install_keda,
        install_operator=args.install_operator,
        install_service_monitor_crd=args.install_service_monitor_crd,
        operator_chart_version=args.operator_chart_version,
        operator_chart_path=args.operator_chart_path,
        registry_server=args.registry_server,
        registry_username=args.registry_username,
        registry_password=args.registry_password,
        registry_email=args.registry_email,
        airflow_image=args.airflow_image,
        airflow_version=args.airflow_version,
        executor=executor,
        apply_cr=args.apply_cr,
        cr_path=args.cr_path,
        pod_template_path=Path(args.pod_template_file) if args.pod_template_file else None,
        create_admin_user=args.create_admin_user,
        admin_username=args.admin_username,
        admin_password=args.admin_password,
        admin_email=args.admin_email,
    )

    ms = Milestones()

    try:
        # 1. Prerequisites
        h = ms.start("Validate prerequisites")
        _validate_prereqs(need_k3d=creating_cluster)
        ms.done(h)

        # 2-4. k3d cluster creation (only when --cluster-name is given)
        registry_config: Path | None = None
        if creating_cluster:
            h = ms.start(f"Ensure Docker network `{settings.docker_network}`")
            _ensure_docker_network(settings.docker_network)
            ms.done(h)

            if not settings.no_local_registry:
                h = ms.start("Ensure local pull-through registry proxies")
                _ensure_local_registries(settings.docker_network)
                registry_config = _get_registry_config_path()
                ms.done(h, detail=f"config={registry_config}")
            else:
                ms.skip("Local registry proxies", reason="--no-local-registry set")

            h = ms.start(f"Create k3d cluster `{settings.cluster_name}`")
            if settings.recreate_cluster:
                _delete_k3d_cluster(settings.cluster_name)
            if not _k3d_cluster_exists(settings.cluster_name):
                _k3d_create_cluster(
                    name=settings.cluster_name,
                    docker_network=settings.docker_network,
                    https_port=settings.https_port,
                    http_port=settings.http_port,
                    agents=settings.agents,
                    registry_config=registry_config,
                )
            else:
                _debug(f"Cluster already exists, skipping creation: {settings.cluster_name}")
            ms.done(h, detail=f"context={settings.context}")
        else:
            ms.skip("Docker network", reason="--cluster-name not set")
            ms.skip("Local registry proxies", reason="--cluster-name not set")
            ms.skip("Create k3d cluster", reason="--cluster-name not set")

        # 5. Deployment namespace
        h = ms.start(f"Create deployment namespace `{settings.namespace}`")
        _create_namespace(settings.context, settings.namespace)
        ms.done(h)

        # 6. cert-manager
        if not args.skip_cert_manager:
            h = ms.start(f"Install cert-manager {CERT_MANAGER_VERSION}")
            _install_cert_manager(settings.context)
            _pin_cert_manager_to_control_plane(settings.context)
            _wait_for_cert_manager(settings.context)
            ms.done(h, detail=f"version={CERT_MANAGER_VERSION}")
        else:
            ms.skip(f"Install cert-manager {CERT_MANAGER_VERSION}", reason="--skip-cert-manager set")

        # 6b. ServiceMonitor CRD (so the operator's apiserver watch can sync).
        # Installed before the operator so the CRD exists when its controllers start.
        if settings.install_service_monitor_crd:
            h = ms.start("Install ServiceMonitor CRD (monitoring.coreos.com/v1)")
            _install_service_monitor_crd(settings.context)
            ms.done(h, detail=f"prometheus-operator {PROMETHEUS_OPERATOR_VERSION}")
        else:
            ms.skip("Install ServiceMonitor CRD", reason="--no-service-monitor-crd set")

        # 7. Operator Helm chart.
        # Prefer the in-repo chart: it ships the RBAC + CRDs that match the operator image, so
        # the ClusterRole grants every resource the controller watches (apiservers,
        # eventschedulers, servicemonitors, …). The remote chart can lag the image and leave the
        # ClusterRole missing rules → "forbidden"/"no matches for kind" at runtime.
        if settings.install_operator:
            local_chart = _find_local_operator_chart(settings.operator_chart_path)
            if local_chart:
                operator_chart = str(local_chart)
                chart_source = f"local ({local_chart})"
            else:
                operator_chart = f"{OPERATOR_HELM_REPO_NAME}/{OPERATOR_CHART_NAME}"
                chart_source = f"remote ({OPERATOR_HELM_REPO_URL})"
                _print(
                    "  ⚠️  Local operator chart not found — falling back to the REMOTE chart. Its RBAC "
                    "and CRDs may lag the operator image, which causes 'forbidden'/'no matches for kind' "
                    "errors at runtime. Pass --operator-chart-path <repo>/airflow-operator/helm to use "
                    "the in-repo chart."
                )
                _helm_repo_add(OPERATOR_HELM_REPO_NAME, OPERATOR_HELM_REPO_URL)

            h = ms.start(f"Install airflow-operator (ns={settings.operator_namespace})")
            _helm_upgrade_install(
                context=settings.context,
                release=settings.operator_release,
                chart=operator_chart,
                namespace=settings.operator_namespace,
                version=settings.operator_chart_version if not local_chart else "",
                timeout="10m",
            )
            ms.done(h, detail=f"release={settings.operator_release} chart={chart_source}")
        else:
            ms.skip("Install airflow-operator", reason="--no-install-operator set")

        # 8. KEDA
        if settings.install_keda:
            h = ms.start(f"Install KEDA (ns={settings.keda_namespace})")
            _helm_repo_add(KEDA_HELM_REPO_NAME, KEDA_HELM_REPO_URL)
            _helm_upgrade_install(
                context=settings.context,
                release="keda",
                chart=f"{KEDA_HELM_REPO_NAME}/{KEDA_CHART_NAME}",
                namespace=settings.keda_namespace,
                timeout="5m",
            )
            ms.done(h)
        else:
            ms.skip("Install KEDA", reason="pass --install-keda to enable CeleryWorker autoscaling")

        # 9. Secrets
        if not args.skip_secrets:
            h = ms.start(f"Create Secrets in `{settings.namespace}`")
            state = _load_state(settings.namespace)
            _setup_secrets(settings, state)
            _save_state(settings.namespace, state)
            ms.done(h, detail=f"state={_state_path(settings.namespace)}")
        else:
            ms.skip("Create Secrets", reason="--skip-secrets set")

        # 10. Pod template ConfigMap
        if settings.pod_template_path is not None:
            h = ms.start("Create KubernetesExecutor pod template ConfigMap")
            _apply_configmap_from_file(
                context=settings.context,
                namespace=settings.namespace,
                name=f"{settings.release_prefix}-kexec-pod-template",
                key="pod_template_file.yaml",
                file_path=settings.pod_template_path,
            )
            ms.done(h, detail=f"configmap={settings.release_prefix}-kexec-pod-template")
        else:
            ms.skip("KubernetesExecutor pod template ConfigMap", reason="--pod-template-file not set")

        # 10b. In-cluster postgres: clear a stale password volume before (re)applying the CR.
        if settings.in_cluster_postgres:
            h = ms.start("Check in-cluster postgres volume state")
            detail = _cleanup_stale_postgres_pvc(settings)
            ms.done(h, detail=detail or "nothing to do")
        else:
            ms.skip("Check in-cluster postgres volume state", reason="external metadata DB in use")

        # 11. Apply Airflow CR
        if settings.apply_cr:
            if settings.cr_path:
                cr_file = Path(settings.cr_path)
                if not cr_file.exists():
                    raise RuntimeError(f"CR file not found: {cr_file}")
                h = ms.start(f"Apply Airflow CR ({cr_file.name})")
                _run(["kubectl", "--context", settings.context, "apply", "-f", str(cr_file)], capture=False)
                ms.done(h, detail=str(cr_file))
            else:
                h = ms.start("Apply generated Airflow CR")
                cr_yaml = _generate_cr_yaml(settings)
                _kubectl_apply_yaml(settings.context, cr_yaml)
                ms.done(h, detail=f"name={settings.release_prefix} ns={settings.namespace}")
        else:
            ms.skip("Apply Airflow CR", reason="--no-apply-cr set")

        # 12. Create Airflow admin user (Airflow 2 / FAB auth)
        if settings.create_admin_user and settings.apply_cr:
            h = ms.start("Create Airflow admin user")
            detail = _create_admin_user(settings)
            ms.done(h, detail=detail)
        elif settings.create_admin_user:
            ms.skip("Create Airflow admin user", reason="--no-apply-cr set (no webserver to create the user in)")
        else:
            ms.skip("Create Airflow admin user", reason="pass --create-admin-user to enable")

        ms.print_summary_table()

        # Access instructions
        _print("\nNext steps:")
        if settings.apply_cr:
            _print(f"""
  Watch the Airflow CR come up:
    kubectl --context {settings.context} -n {settings.namespace} get airflow -w

  Access the Airflow webserver (port-forward):
    kubectl --context {settings.context} -n {settings.namespace} \\
      port-forward svc/{settings.release_prefix}-webserver 8888:8080
    # Then open http://localhost:8888
""")
            if settings.create_admin_user:
                _print(f"  Log in with: {settings.admin_username} / {settings.admin_password}\n")
            else:
                _print(f"""  No admin user was created. Create one (or re-run with --create-admin-user):
    kubectl --context {settings.context} -n {settings.namespace} exec deployment/{settings.release_prefix}-webserver -- \\
      airflow users create --username admin --password admin \\
        --firstname Admin --lastname User --role Admin --email admin@example.com
""")
        else:
            _print(f"""
  Apply the Airflow CR manually (generate + inspect first):
    python3 -c "
import sys; sys.argv=['x','--in-cluster-postgres','--cluster-name','x']
import setup_operator_standalone as s
print(s._generate_cr_yaml(...))"  # or just --apply-cr on your next run
""")
        _print(f"""  Operator logs:
    kubectl --context {settings.context} -n {settings.operator_namespace} logs -l app.kubernetes.io/name=airflow-operator -f
""")
        _print("✅ Completed.")
        return 0

    except Exception as e:  # noqa: BLE001
        ms.fail_active_if_any(error=str(e))
        ms.print_summary_table()
        _print(f"\n❌ Failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
