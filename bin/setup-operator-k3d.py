#!/usr/bin/env python3
"""
Local setup for Astronomer APC with Airflow Operator enabled, using a single k3d cluster.

This script creates a unified-plane cluster with:
- Airflow Operator CRDs, webhooks, and controller
- cert-manager (required by operator webhooks)
- All standard APC components (Houston, Commander, UI, etc.)

Usage:
    python3 bin/setup-operator-k3d.py
    python3 bin/setup-operator-k3d.py --base-domain local.astro.dev
    python3 bin/setup-operator-k3d.py --airflow-db mysql
    python3 bin/setup-operator-k3d.py --recreate-cluster
    python3 bin/setup-operator-k3d.py --skip-certs --skip-clusters

Based on the patterns from bin/setup-cp-dp-k3d.py.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

GIT_ROOT_DIR = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)
HELPER_DIR = Path.home() / ".local" / "share" / "astronomer-software"
REGISTRY_CONFIG_DIR = HELPER_DIR / "registry-configs"
K3D_REGISTRY_CONFIG_PATH = HELPER_DIR / "k3d-registry.yaml"
REGISTRY_IMAGE = "registry:2"


# ---------------------------------------------------------------------------
# Pull-through registry proxies (same as setup-cp-dp-k3d.py)
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
)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    base_domain: str
    namespace: str
    release_name: str
    cluster_name: str
    docker_network: str
    https_port: int
    http_port: int
    tls_secret_name: str
    mkcert_root_ca_secret_name: str
    mkcert_root_ca_secret_key: str
    helm_timeout: str
    helm_debug: bool
    airflow_db: str
    helm_values_files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print(msg: str) -> None:
    print(msg, flush=True)


def _debug_enabled() -> bool:
    return os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"}


def _debug(msg: str) -> None:
    if _debug_enabled():
        _print(f"DEBUG: {msg}")


def _ts() -> str:
    """Return a compact local timestamp for progress logs."""
    return time.strftime("%H:%M:%S")


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
    """
    Run a command and optionally capture stdout/stderr.
    """
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


# ---------------------------------------------------------------------------
# Milestone logger (matches setup-cp-dp-k3d.py format)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MilestoneHandle:
    idx: int


class Milestones:
    """
    Milestone logger:
    - Minimal live output
    - Final summary table with status icons
    """

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
        _print(f"\n⏳ [{h.idx:02d}] {title}")
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
# Prerequisites
# ---------------------------------------------------------------------------


def _validate_prereqs() -> None:
    _require_executable("docker", hint="Install Docker Desktop/OrbStack and ensure `docker` works.")
    _require_executable("k3d", hint="Install k3d (e.g. `brew install k3d` on macOS).")
    _require_executable("kubectl", hint="Install kubectl and ensure it is in PATH.")
    _require_executable("helm", hint="Install helm and ensure it is in PATH.")
    _require_executable("mkcert", hint="Install mkcert (e.g. `brew install mkcert && mkcert -install` on macOS).")


# ---------------------------------------------------------------------------
# Docker network
# ---------------------------------------------------------------------------


def _docker_network_exists(name: str) -> bool:
    proc = _run(["docker", "network", "inspect", name], check=False)
    return proc.returncode == 0


def _ensure_docker_network(name: str) -> None:
    if _docker_network_exists(name):
        return
    _print(f"Creating Docker network: {name}")
    _run(["docker", "network", "create", name], check=True)


# ---------------------------------------------------------------------------
# Registry proxies
# ---------------------------------------------------------------------------


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
        nets = _container_networks(spec.name)
        if docker_network not in nets:
            _run(["docker", "network", "connect", docker_network, spec.name], check=False)
        return

    if state == "exited":
        _run(["docker", "start", spec.name])
        nets = _container_networks(spec.name)
        if docker_network not in nets:
            _run(["docker", "network", "connect", docker_network, spec.name], check=False)
        return

    REGISTRY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_registry_docker_config(spec))
    _run(["docker", "volume", "create", volume_name], check=False)
    _run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            spec.name,
            "--network",
            docker_network,
            "-p",
            f"{spec.host_port}:5000",
            "-v",
            f"{config_path}:/etc/docker/registry/config.yml:ro",
            "-v",
            f"{volume_name}:/var/lib/registry",
            "--restart",
            "unless-stopped",
            REGISTRY_IMAGE,
        ]
    )


def _ensure_local_registries(docker_network: str) -> None:
    for spec in _REGISTRY_SPECS:
        _ensure_registry(spec, docker_network)


def _get_registry_config_path(docker_network: str) -> Path:
    """Write k3d containerd mirror config and return path."""
    k3d_config = {
        "mirrors": {
            "quay.io": {"endpoint": [f"http://{_REGISTRY_SPECS[0].name}:5000"]},
            "docker.io": {"endpoint": [f"http://{_REGISTRY_SPECS[1].name}:5000"]},
            "docker.elastic.co": {"endpoint": [f"http://{_REGISTRY_SPECS[2].name}:5000"]},
            "registry.k8s.io": {"endpoint": [f"http://{_REGISTRY_SPECS[3].name}:5000"]},
        }
    }
    K3D_REGISTRY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    import yaml

    K3D_REGISTRY_CONFIG_PATH.write_text(yaml.dump(k3d_config, default_flow_style=False))
    return K3D_REGISTRY_CONFIG_PATH


# ---------------------------------------------------------------------------
# TLS certificates
# ---------------------------------------------------------------------------


def _generate_tls_certs(s: Settings) -> Path:
    cert_dir = HELPER_DIR / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_file = cert_dir / "tls.crt"
    key_file = cert_dir / "tls.key"

    sans = [s.base_domain, f"*.{s.base_domain}"]
    _run(["mkcert", "-cert-file", str(cert_file), "-key-file", str(key_file), *sans])

    # Append root CA for full chain
    proc = _run(["mkcert", "-CAROOT"])
    ca_root = (proc.stdout or "").strip()
    root_ca_path = Path(ca_root) / "rootCA.pem"
    with open(cert_file, "a") as f:
        f.write(root_ca_path.read_text())

    return cert_dir


def _mkcert_root_ca_path() -> Path:
    proc = _run(["mkcert", "-CAROOT"])
    return Path((proc.stdout or "").strip()) / "rootCA.pem"


# ---------------------------------------------------------------------------
# k3d cluster
# ---------------------------------------------------------------------------


def _k3d_cluster_exists(cluster_name: str) -> bool:
    proc = _run(["k3d", "cluster", "list", "-o", "json"], check=False)
    if proc.returncode != 0:
        return False
    try:
        clusters = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return False
    return any(c.get("name") == cluster_name for c in clusters)


def _create_cluster(s: Settings, *, registry_config: Path | None) -> None:
    if _k3d_cluster_exists(s.cluster_name):
        _print(f"Cluster '{s.cluster_name}' already exists, switching context.")
        _run(["kubectl", "config", "use-context", f"k3d-{s.cluster_name}"])
        return

    root_ca = _mkcert_root_ca_path()
    volume = f"{root_ca}:/etc/ssl/certs/mkcert-rootCA.pem@server:*"

    cmd = [
        "k3d",
        "cluster",
        "create",
        s.cluster_name,
        "--network",
        s.docker_network,
        "--k3s-arg",
        "--disable=traefik@server:0",
        "--volume",
        volume,
        "--port",
        f"{s.https_port}:443@loadbalancer",
        "--port",
        f"{s.http_port}:80@loadbalancer",
    ]

    # Pull-through registry config
    if registry_config and registry_config.exists():
        cmd += ["--registry-config", str(registry_config)]

    _print(f"Creating k3d cluster: {s.cluster_name}")
    _run(cmd, check=True, capture=True)
    _run(["kubectl", "config", "use-context", f"k3d-{s.cluster_name}"])


def _delete_cluster(cluster_name: str) -> None:
    _run(["k3d", "cluster", "delete", cluster_name], check=False, capture=False)


# ---------------------------------------------------------------------------
# Namespace + secrets
# ---------------------------------------------------------------------------


def _kubectl_create_namespace(namespace: str) -> None:
    proc = _run(["kubectl", "create", "namespace", namespace], check=False)
    if proc.returncode == 0:
        return
    if "AlreadyExists" in (proc.stderr or ""):
        return
    raise CommandError(f"Failed to create namespace {namespace}: {(proc.stderr or '').strip()}")


def _kubectl_apply_tls_secret(
    *,
    namespace: str,
    secret_name: str,
    cert_file: Path,
    key_file: Path,
) -> None:
    """Create or update a TLS secret idempotently via dry-run + apply."""
    proc = _run(
        [
            "kubectl",
            "create",
            "secret",
            "tls",
            secret_name,
            "--cert",
            str(cert_file),
            "--key",
            str(key_file),
            "-n",
            namespace,
            "--dry-run=client",
            "-o",
            "yaml",
        ]
    )
    _run(["kubectl", "apply", "-f", "-"], stdin=proc.stdout)
    _debug(f"TLS secret applied: {secret_name} in {namespace}")


def _kubectl_apply_generic_secret(
    *,
    namespace: str,
    secret_name: str,
    from_file_key: str,
    from_file_path: Path,
) -> None:
    """Create or update a generic secret idempotently via dry-run + apply."""
    proc = _run(
        [
            "kubectl",
            "create",
            "secret",
            "generic",
            secret_name,
            f"--from-file={from_file_key}={from_file_path}",
            "-n",
            namespace,
            "--dry-run=client",
            "-o",
            "yaml",
        ]
    )
    _run(["kubectl", "apply", "-f", "-"], stdin=proc.stdout)


def _create_namespace_and_secrets(s: Settings) -> None:
    _kubectl_create_namespace(s.namespace)

    cert_dir = HELPER_DIR / "certs"
    cert_file = cert_dir / "tls.crt"
    key_file = cert_dir / "tls.key"

    if cert_file.exists() and key_file.exists():
        _kubectl_apply_tls_secret(
            namespace=s.namespace,
            secret_name=s.tls_secret_name,
            cert_file=cert_file,
            key_file=key_file,
        )

    root_ca = _mkcert_root_ca_path()
    if root_ca.exists():
        _kubectl_apply_generic_secret(
            namespace=s.namespace,
            secret_name=s.mkcert_root_ca_secret_name,
            from_file_key=s.mkcert_root_ca_secret_key,
            from_file_path=root_ca,
        )


# ---------------------------------------------------------------------------
# cert-manager (required by operator webhooks)
# ---------------------------------------------------------------------------

CERT_MANAGER_VERSION = "v1.5.4"
CERT_MANAGER_MANIFEST_URL = f"https://github.com/jetstack/cert-manager/releases/download/{CERT_MANAGER_VERSION}/cert-manager.yaml"


def _install_cert_manager() -> None:
    """Install cert-manager CRDs + controller. Idempotent (kubectl apply)."""
    _print(f"Installing cert-manager {CERT_MANAGER_VERSION}")
    _run(["kubectl", "apply", "-f", CERT_MANAGER_MANIFEST_URL], capture=False)


def _wait_for_cert_manager(timeout_s: int = 120) -> None:
    """Wait for cert-manager deployment to be available."""
    _print("Waiting for cert-manager to be ready...")
    _run(
        [
            "kubectl",
            "wait",
            "-n",
            "cert-manager",
            "deployment/cert-manager",
            "--for",
            "condition=available",
            f"--timeout={timeout_s}s",
        ],
        capture=False,
    )
    _run(
        [
            "kubectl",
            "wait",
            "-n",
            "cert-manager",
            "deployment/cert-manager-webhook",
            "--for",
            "condition=available",
            f"--timeout={timeout_s}s",
        ],
        capture=False,
    )
    _print("cert-manager is ready.")


# ---------------------------------------------------------------------------
# Helm values generation
# ---------------------------------------------------------------------------


def _generate_helm_values(s: Settings, values_dir: Path) -> Path:
    values = {
        "global": {
            "plane": {"mode": "unified"},
            "baseDomain": s.base_domain,
            "tlsSecret": s.tls_secret_name,
            "airflowOperator": {"enabled": True},
            "postgresql": {"enabled": True},
            "rbac": {"enabled": True},
            "clusterRoles": True,
            "networkPolicy": {"enabled": True},
            "platformNodePool": {
                "nodeSelector": {},
                "affinity": {},
                "tolerations": [],
            },
            "podDisruptionBudgets": {"enabled": False},
        },
        "airflow-operator": {
            "crd": {"create": True},
            "certManager": {"enabled": True},
            "images": {
                "manager": {
                    "repository": "quay.io/astronomer/airflow-operator-controller",
                    "tag": "1.5.2",
                },
            },
            "manager": {
                "replicas": 1,
                "resources": {
                    "limits": {"cpu": "600m", "memory": "500Mi"},
                    "requests": {"cpu": "200m", "memory": "128Mi"},
                },
            },
        },
        "astronomer": {
            "houston": {"replicas": 1},
            "astroUI": {"replicas": 1},
            "commander": {"replicas": 1},
            "registry": {"replicas": 1},
            "dpLink": {"enabled": False},
        },
        "nginx": {"replicas": 1},
        "elasticsearch": {
            "images": {
                "es": {
                    "repository": "docker.elastic.co/elasticsearch/elasticsearch",
                    "tag": "8.19.12",
                },
            },
            "client": {"replicas": 1},
            "master": {"replicas": 1},
            "data": {"replicas": 1},
        },
        "nats": {"replicas": 1},
    }

    import yaml

    values_file = values_dir / "operator-values.yaml"
    values_file.write_text(yaml.dump(values, default_flow_style=False))
    _print(f"Generated values file: {values_file}")
    return values_file


# ---------------------------------------------------------------------------
# Helm install
# ---------------------------------------------------------------------------


def _helm_upgrade_install(
    *,
    chart_dir: Path,
    release_name: str,
    namespace: str,
    values_file: Path,
    extra_values_files: list[Path],
    timeout: str,
    debug: bool,
) -> None:
    cmd = [
        "helm",
        "upgrade",
        "--install",
        release_name,
        str(chart_dir),
        "--namespace",
        namespace,
        "--values",
        str(values_file),
        "--timeout",
        timeout,
        "--wait",
    ]
    for extra in extra_values_files:
        cmd.extend(["--values", str(extra)])
    if debug:
        cmd.append("--debug")
    _print(f"Helm upgrade/install: {release_name} in ns={namespace}")
    _run(cmd, check=True, capture=False)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _verify_operator(s: Settings) -> bool:
    ok = True

    # Check operator pod
    proc = _run(
        [
            "kubectl",
            "get",
            "pods",
            "-n",
            s.namespace,
            "-l",
            "app=airflow-operator-controller-manager",
            "-o",
            "jsonpath={.items[0].status.phase}",
        ],
        check=False,
    )
    pod_phase = (proc.stdout or "").strip()
    if pod_phase == "Running":
        _print("  Operator pod: Running")
    else:
        _print(f"  Operator pod: {pod_phase or 'NOT FOUND'}")
        ok = False

    # Check CRDs
    proc = _run(["kubectl", "get", "crds", "-o", "name"], check=False)
    crds = [line for line in (proc.stdout or "").strip().split("\n") if "airflow.apache.org" in line]
    _print(f"  Airflow CRDs installed: {len(crds)}")
    if len(crds) < 10:
        _print("  WARNING: Expected at least 10 Airflow CRDs")
        ok = False

    # Check webhooks
    proc = _run(["kubectl", "get", "validatingwebhookconfigurations", "-o", "name"], check=False)
    vwh = [line for line in (proc.stdout or "").strip().split("\n") if "airflow" in line.lower()]
    _print(f"  Validating webhooks: {len(vwh)}")

    proc = _run(["kubectl", "get", "mutatingwebhookconfigurations", "-o", "name"], check=False)
    mwh = [line for line in (proc.stdout or "").strip().split("\n") if "airflow" in line.lower()]
    _print(f"  Mutating webhooks: {len(mwh)}")

    return ok


# ---------------------------------------------------------------------------
# Host instructions
# ---------------------------------------------------------------------------


def _print_host_etc_hosts_instructions(s: Settings) -> None:
    _print(f"""
Add the following to /etc/hosts (or use dnsmasq):

  127.0.0.1  {s.base_domain} app.{s.base_domain} houston.{s.base_domain} grafana.{s.base_domain} registry.{s.base_domain} install.{s.base_domain}

Access the UI:            https://app.{s.base_domain}
Access Houston API:       https://houston.{s.base_domain}/v1

Create an operator deployment:
  - Via UI: New Deployment -> Mode: Operator
  - Via GraphQL: See docs/operator/02-local-setup.md

Inspect operator resources:
  kubectl get airflows -A
  kubectl logs -n {s.namespace} -l app=airflow-operator-controller-manager --tail=50
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Setup APC + Airflow Operator on k3d")
    p.add_argument("--base-domain", default="localtest.me")
    p.add_argument("--namespace", default="astronomer")
    p.add_argument("--release-name", default="astronomer")
    p.add_argument("--cluster-name", default="operator-dev")
    p.add_argument("--docker-network", default="astronomer-net")
    p.add_argument("--https-port", type=int, default=443)
    p.add_argument("--http-port", type=int, default=80)
    p.add_argument("--airflow-db", choices=["postgres", "mysql"], default="postgres")
    p.add_argument("--helm-timeout", default="60m")
    p.add_argument("--helm-debug", action="store_true")
    p.add_argument("--helm-values", action="append", default=[], help="Extra values files (can repeat)")
    p.add_argument("--recreate-cluster", action="store_true")
    p.add_argument("--no-local-registry", action="store_true")
    p.add_argument("--skip-certs", action="store_true")
    p.add_argument("--skip-clusters", action="store_true")
    p.add_argument("--skip-secrets", action="store_true")
    p.add_argument("--skip-helm", action="store_true")
    p.add_argument("--values-dir", default=None, help="Dir for generated values (default: temp)")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if GIT_ROOT_DIR is None:
        raise RuntimeError("Could not locate repo root (missing .git).")

    ms = Milestones()

    s = Settings(
        base_domain=args.base_domain,
        namespace=args.namespace,
        release_name=args.release_name,
        cluster_name=args.cluster_name,
        docker_network=args.docker_network,
        https_port=args.https_port,
        http_port=args.http_port,
        tls_secret_name=f"{args.release_name}-tls",
        mkcert_root_ca_secret_name="mkcert-root-ca",
        mkcert_root_ca_secret_key="ca.crt",
        helm_timeout=args.helm_timeout,
        helm_debug=args.helm_debug,
        airflow_db=args.airflow_db,
        helm_values_files=args.helm_values,
    )

    values_dir = Path(args.values_dir) if args.values_dir else Path(tempfile.mkdtemp(prefix="operator-k3d-"))
    values_dir.mkdir(parents=True, exist_ok=True)

    _print(f"""
Astronomer APC + Airflow Operator Setup
========================================
  Cluster:    {s.cluster_name}
  Domain:     {s.base_domain}
  Namespace:  {s.namespace}
  Airflow DB: {s.airflow_db}
  Values dir: {values_dir}
""")

    try:
        # Step: Prerequisites
        h = ms.start("Validate prerequisites (docker/k3d/kubectl/helm/mkcert)")
        _validate_prereqs()
        ms.done(h)

        # Step: Docker network
        h = ms.start(f"Ensure Docker network `{s.docker_network}` exists")
        _ensure_docker_network(s.docker_network)
        ms.done(h)

        # Step: Registry proxies
        registry_config: Path | None = None
        if not args.no_local_registry:
            h = ms.start("Ensure local pull-through registry proxy containers are running")
            _ensure_local_registries(s.docker_network)
            registry_config = _get_registry_config_path(s.docker_network)
            ms.done(h, detail=f"config={registry_config}")
        else:
            ms.skip("Ensure local pull-through registry proxy containers are running", reason="--no-local-registry set")

        # Step: TLS certs
        if not args.skip_certs:
            h = ms.start(f"Generate TLS certificates (mkcert) for *.{s.base_domain}")
            _generate_tls_certs(s)
            ms.done(h)
        else:
            ms.skip(f"Generate TLS certificates (mkcert) for *.{s.base_domain}", reason="--skip-certs set")

        # Step: Cluster creation
        if not args.skip_clusters:
            if args.recreate_cluster:
                h = ms.start(f"Delete existing cluster `{s.cluster_name}`")
                _delete_cluster(s.cluster_name)
                ms.done(h)
            h = ms.start(f"Create k3d cluster `{s.cluster_name}`")
            _create_cluster(s, registry_config=registry_config)
            ms.done(h)
        else:
            ms.skip(f"Create k3d cluster `{s.cluster_name}`", reason="--skip-clusters set")

        # Step: Namespace + secrets
        if not args.skip_secrets:
            h = ms.start(f"Create namespace `{s.namespace}` + TLS/CA secrets")
            _create_namespace_and_secrets(s)
            ms.done(h)
        else:
            ms.skip(f"Create namespace `{s.namespace}` + TLS/CA secrets", reason="--skip-secrets set")

        # Step: cert-manager (required by operator webhooks)
        if not args.skip_helm:
            h = ms.start(f"Install cert-manager {CERT_MANAGER_VERSION} (required by operator webhooks)")
            _install_cert_manager()
            _wait_for_cert_manager()
            ms.done(h)
        else:
            ms.skip(f"Install cert-manager {CERT_MANAGER_VERSION}", reason="--skip-helm set")

        # Step: Generate Helm values
        h = ms.start("Generate Helm values (operator enabled)")
        values_file = _generate_helm_values(s, values_dir)
        ms.done(h, detail=str(values_file))

        # Step: Helm install
        if not args.skip_helm:
            h = ms.start(f"Helm upgrade/install `{s.release_name}` (this may take 10-30 minutes)")
            _helm_upgrade_install(
                chart_dir=GIT_ROOT_DIR,
                release_name=s.release_name,
                namespace=s.namespace,
                values_file=values_file,
                extra_values_files=[Path(f) for f in args.helm_values],
                timeout=s.helm_timeout,
                debug=s.helm_debug,
            )
            ms.done(h)
        else:
            ms.skip(f"Helm upgrade/install `{s.release_name}`", reason="--skip-helm set")

        # Step: Verification
        h = ms.start("Verify operator installation")
        if _verify_operator(s):
            ms.done(h, detail="All checks passed")
        else:
            ms.done(h, detail="Some checks failed — see output above")

        ms.print_summary_table()
        _print_host_etc_hosts_instructions(s)
        _print("\n✅ Completed.")
        return 0
    except Exception as e:  # noqa: BLE001
        ms.fail_active_if_any(error=str(e))
        ms.print_summary_table()
        _print(f"\n❌ Failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
