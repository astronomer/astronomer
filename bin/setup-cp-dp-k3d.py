#!/usr/bin/env python3
"""
One-shot local CP/DP setup for Astronomer using two k3d clusters.

This script automates the workflow documented in `docs/cp-dp-k3d-setup-guide.md`:
- Generate TLS certs (mkcert) with the right SANs for CP + DP subdomains
- Create two k3d clusters on the same Docker network
- Create namespaces + secrets (TLS + mkcert root CA) in both clusters
- Install Astronomer chart into both clusters (CP: unified, DP: data)
- Reconcile cross-cluster DNS + node-level hosts (OrbStack-friendly) using existing helper

Notes / constraints:
- We intentionally do NOT modify `/etc/hosts` on the local machine (sudo). The guide covers that manually.
- We do NOT install k3d/helm/kubectl/mkcert for you by default; we validate and fail with actionable messages.
- Safe to re-run: cluster/secrets/helm installs are done in an idempotent way.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


GIT_ROOT_DIR = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)
HELPER_DIR = Path.home() / ".local" / "share" / "astronomer-software"
HELPER_BIN_DIR = HELPER_DIR / "bin"


@dataclass(frozen=True)
class Ports:
    cp_https: int
    cp_http: int
    dp_https: int
    dp_http: int


@dataclass(frozen=True)
class ClusterNames:
    cp: str
    dp: str


@dataclass(frozen=True)
class Settings:
    base_domain: str
    dp_domain_prefix: str
    namespace: str
    release_name: str
    docker_network: str
    clusters: ClusterNames
    ports: Ports
    tls_secret_name: str
    mkcert_root_ca_secret_name: str
    mkcert_root_ca_secret_key: str
    helm_timeout: str
    helm_debug: bool


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


@dataclass(frozen=True)
class MilestoneHandle:
    idx: int


class Milestones:
    """
    Milestone logger:
    - Minimal live output
    - Final summary table with ✅/❌
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
            if max_len <= 3:
                return s[:max_len]
            return s[: max_len - 3] + "..."

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
                details_cell = (details_cell + " " if details_cell else "") + error

            # Keep the table readable in a terminal.
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
    """
    Prefer our helper-installed mkcert if present, otherwise fall back to PATH.
    """
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


def _ensure_tls_certs(settings: Settings) -> tuple[Path, Path, Path]:
    """
    Generate `astronomer-tls.pem` + `astronomer-tls.key` with SANs for:
    - <baseDomain>, *.<baseDomain>
    - <dpPrefix>.<baseDomain>, *.<dpPrefix>.<baseDomain>

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

    # Always regenerate to ensure SANs are correct for the chosen dp domain prefix.
    _print("Generating TLS certificates via mkcert (overwrites existing astronomer-tls.{pem,key})")
    _run([mkcert_exe, "-install"], check=True)

    base = settings.base_domain
    dp = f"{settings.dp_domain_prefix}.{settings.base_domain}"
    sans = [base, f"*.{base}", dp, f"*.{dp}"]

    _run(
        [
            mkcert_exe,
            f"-cert-file={cert_path}",
            f"-key-file={key_path}",
            *sans,
        ],
        check=True,
    )

    # Append mkcert root CA to cert for a full chain (matches `bin/certs.py` behavior).
    # NOTE: mkcert might already include it; we avoid double-appending by a simple guard.
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
) -> None:
    """
    Create a k3d cluster and disable traefik.
    """
    volume = f"{mkcert_root_ca}:/etc/ssl/certs/mkcert-rootCA.pem@server:*"
    cmd = [
        "k3d",
        "cluster",
        "create",
        name,
        "--network",
        docker_network,
        "--k3s-arg",
        "--disable=traefik@server:0",
        "--volume",
        volume,
    ]
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
    """
    Idempotently apply a TLS secret.
    """
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


def _write_values_file(path: Path, content: str) -> None:
    path.write_text(content)


def _cp_values_yaml(settings: Settings) -> str:
    return f"""\
global:
  baseDomain: {settings.base_domain}
  plane:
    mode: unified
    domainPrefix: ""
  tlsSecret: {settings.tls_secret_name}
  postgresqlEnabled: true
  prometheusPostgresExporterEnabled: true
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
  vectorEnabled: true
  elasticsearchEnabled: true
  dagOnlyDeployment:
    enabled: true

tags:
  platform: true
  logging: true
  monitoring: true
  postgresql: true
  nats: true

astronomer:
  astroUI:
    replicas: 1
    env:
      - name: APP_API_LOC_HTTPS
        value: "https://houston.{settings.base_domain}/v1"
      - name: APP_API_LOC_WSS
        value: "wss://houston.{settings.base_domain}/ws"
  houston:
    replicas: 1
    worker:
      replicas: 1
    config:
      emailConfirmation: false
      publicSignups: false
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
    heapMemory: 256m
    resources:
      requests:
        memory: 512Mi

  data:
    replicas: 1
    heapMemory: 512m
    resources:
      requests:
        memory: 1Gi

  client:
    replicas: 1
    heapMemory: 256m
    resources:
      requests:
        memory: 512Mi
  images:
    es:
      repository: docker.elastic.co/elasticsearch/elasticsearch
      tag: "8.18.6"
"""


def _dp_values_yaml(settings: Settings) -> str:
    return f"""\
global:
  baseDomain: {settings.base_domain}
  plane:
    mode: data
    domainPrefix: {settings.dp_domain_prefix}
  tlsSecret: {settings.tls_secret_name}
  postgresqlEnabled: true
  prometheusPostgresExporterEnabled: true
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
  vectorEnabled: true
  elasticsearchEnabled: true
  dagOnlyDeployment:
    enabled: true

tags:
  platform: true
  logging: true
  monitoring: true
  postgresql: true
  nats: true

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
    heapMemory: 256m
    resources:
      requests:
        memory: 512Mi

  data:
    replicas: 1
    heapMemory: 512m
    resources:
      requests:
        memory: 1Gi

  client:
    replicas: 1
    heapMemory: 256m
    resources:
      requests:
        memory: 512Mi
  images:
    es:
      repository: docker.elastic.co/elasticsearch/elasticsearch
      tag: "8.18.6"
"""


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
        "--kube-context",
        context,
        "--values",
        str(values_file),
        "--timeout",
        timeout,
        "--wait",
    ]
    if debug:
        cmd.append("--debug")
    _print(f"Helm upgrade/install ({context}): {release_name} in ns={namespace}")
    _run(cmd, check=True, capture=False)


def _run_dns_reconcile(settings: Settings) -> None:
    """
    Run the existing reconcile helper to pin CoreDNS NodeHosts and the DP node's /etc/hosts.
    """
    script = Path(GIT_ROOT_DIR) / "bin" / "reconcile-k3d-orbstack-network.py"
    env = dict(os.environ)
    env.update(
        {
            "CP_CONTEXT": f"k3d-{settings.clusters.cp}",
            "DP_CONTEXT": f"k3d-{settings.clusters.dp}",
            "PLATFORM_NAMESPACE": settings.namespace,
            "BASE_DOMAIN": settings.base_domain,
            "DP_DOMAIN_PREFIX": settings.dp_domain_prefix,
            "DP_NODE_CONTAINER": f"k3d-{settings.clusters.dp}-server-0",
            "CP_INGRESS_SERVICE": f"{settings.release_name}-cp-nginx",
        }
    )
    _print("Reconciling k3d cross-cluster DNS + node-level hosts pins")
    _run([sys.executable, str(script)], check=True, env=env, capture=False)


def _kubectl_get_service_lb_ip(context: str, namespace: str, service: str) -> str:
    proc = _run(
        [
            "kubectl",
            "--context",
            context,
            "-n",
            namespace,
            "get",
            "svc",
            service,
            "-o",
            "jsonpath={.status.loadBalancer.ingress[0].ip}",
        ],
        check=True,
    )
    ip = proc.stdout.strip()
    if not ip:
        raise RuntimeError(f"Service {namespace}/{service} has no LoadBalancer ingress IP (context={context})")
    return ip


def _ensure_container_hosts_mapping(container: str, ip: str, hostname: str) -> None:
    """
    Ensure a single ip->hostname mapping exists in the container's /etc/hosts.

    /etc/hosts can be regenerated on container restart; safe to run repeatedly.
    """
    sh = (
        "set -eu; "
        + f"grep -qE '^[[:space:]]*{ip}[[:space:]]+.*\\b{hostname}\\b' /etc/hosts "
        + f"|| echo '{ip} {hostname}' >> /etc/hosts"
    )
    _run(["docker", "exec", container, "sh", "-c", sh], check=True)


def _ensure_dp_node_houston_hosts_pin(settings: Settings) -> None:
    """
    Ensure DP node container has node-level DNS pin for `houston.<baseDomain>` -> CP ingress LB IP.

    Why:
    - Pods resolve via CoreDNS, but node-level operations (kubelet/containerd image pulls) use node DNS + /etc/hosts.
    - If `houston.<baseDomain>` resolves incorrectly at the node level, registry auth can break.
    """
    cp_context = f"k3d-{settings.clusters.cp}"
    dp_node_container = f"k3d-{settings.clusters.dp}-server-0"
    cp_nginx_svc = f"{settings.release_name}-cp-nginx"

    cp_nginx_lb_ip = _kubectl_get_service_lb_ip(cp_context, settings.namespace, cp_nginx_svc)
    houston_host = f"houston.{settings.base_domain}"

    _ensure_container_hosts_mapping(dp_node_container, cp_nginx_lb_ip, houston_host)
    _debug(f"Ensured DP node /etc/hosts pin: {cp_nginx_lb_ip} {houston_host}")


def _print_host_etc_hosts_instructions(settings: Settings) -> None:
    """
    Print the recommended /etc/hosts entries for accessing CP/DP from the host machine.

    This uses the k3d Service LoadBalancer IPs for the CP/DP nginx services.
    """
    cp_context = f"k3d-{settings.clusters.cp}"
    dp_context = f"k3d-{settings.clusters.dp}"
    cp_nginx_svc = f"{settings.release_name}-cp-nginx"
    dp_nginx_svc = f"{settings.release_name}-dp-nginx"

    cp_nginx_lb_ip = _kubectl_get_service_lb_ip(cp_context, settings.namespace, cp_nginx_svc)
    dp_nginx_lb_ip = _kubectl_get_service_lb_ip(dp_context, settings.namespace, dp_nginx_svc)

    base = settings.base_domain
    dp = settings.dp_domain_prefix

    _print("\nAdd the following entries to your host `/etc/hosts` (if your host can route to these LB IPs):\n")
    _print(
        f"{dp_nginx_lb_ip} {dp}.{base} deployments.{dp}.{base} registry.{dp}.{base} commander.{dp}.{base} prometheus.{dp}.{base} prom-proxy.{dp}.{base} elasticsearch.{dp}.{base}"
    )
    _print(f"{cp_nginx_lb_ip} {base} app.{base} houston.{base} grafana.{base} prometheus.{base} elasticsearch.{base} alertmanager.{base} registry.{base}")


def _validate_prereqs() -> None:
    _require_executable("docker", hint="Install Docker Desktop/OrbStack and ensure `docker` works.")
    _require_executable("k3d", hint="Install k3d (e.g. `brew install k3d` on macOS).")
    _require_executable("kubectl", hint="Install kubectl and ensure it is in PATH.")
    _require_executable("helm", hint="Install helm and ensure it is in PATH.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automate Astronomer CP/DP local setup using k3d.")
    parser.add_argument("--base-domain", default="localtest.me")
    parser.add_argument("--dp-domain-prefix", default="dp01")
    parser.add_argument("--namespace", default="astronomer")
    parser.add_argument("--release-name", default="astronomer")
    parser.add_argument("--docker-network", default="astronomer-net")
    parser.add_argument("--cp-cluster-name", default="control")
    parser.add_argument("--dp-cluster-name", default="data")

    parser.add_argument("--cp-https-port", type=int, default=8443)
    parser.add_argument("--cp-http-port", type=int, default=8080)
    parser.add_argument("--dp-https-port", type=int, default=8444)
    parser.add_argument("--dp-http-port", type=int, default=8081)

    parser.add_argument("--tls-secret-name", default="astronomer-tls")
    parser.add_argument("--mkcert-root-ca-secret-name", default="mkcert-root-ca")
    parser.add_argument("--mkcert-root-ca-secret-key", default="cert.pem")

    parser.add_argument("--helm-timeout", default=os.environ.get("HELM_TIMEOUT", "60m"))
    parser.add_argument("--helm-debug", action="store_true")
    parser.add_argument(
        "--helm-deps-update",
        action="store_true",
        help="Run `helm dependency update` before installing (off by default; local charts are already vendored).",
    )

    parser.add_argument("--recreate-clusters", action="store_true", help="Delete and recreate k3d clusters if they exist")

    parser.add_argument("--skip-certs", action="store_true")
    parser.add_argument("--skip-clusters", action="store_true")
    parser.add_argument("--skip-secrets", action="store_true")
    parser.add_argument("--skip-helm", action="store_true")
    parser.add_argument("--skip-dns-reconcile", action="store_true")
    parser.add_argument(
        "--skip-node-registry-check",
        action="store_true",
        help="Skip DP node /etc/hosts pin + registry authorization endpoint check.",
    )

    parser.add_argument(
        "--values-dir",
        default="",
        help="Directory to write cp-values.yaml + dp-values.yaml. Defaults to a temp directory.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if GIT_ROOT_DIR is None:
        raise RuntimeError("Could not locate repo root (missing .git).")

    ms = Milestones()

    settings = Settings(
        base_domain=args.base_domain,
        dp_domain_prefix=args.dp_domain_prefix,
        namespace=args.namespace,
        release_name=args.release_name,
        docker_network=args.docker_network,
        clusters=ClusterNames(cp=args.cp_cluster_name, dp=args.dp_cluster_name),
        ports=Ports(cp_https=args.cp_https_port, cp_http=args.cp_http_port, dp_https=args.dp_https_port, dp_http=args.dp_http_port),
        tls_secret_name=args.tls_secret_name,
        mkcert_root_ca_secret_name=args.mkcert_root_ca_secret_name,
        mkcert_root_ca_secret_key=args.mkcert_root_ca_secret_key,
        helm_timeout=args.helm_timeout,
        helm_debug=bool(args.helm_debug),
    )

    try:
        h = ms.start("Validate prerequisites (docker/k3d/kubectl/helm)")
        _validate_prereqs()
        ms.done(h)

        # Step: Docker network
        h = ms.start(f"Ensure Docker network `{settings.docker_network}` exists")
        _ensure_docker_network(settings.docker_network)
        ms.done(h)

        # Step: TLS + mkcert root CA file
        cert_path: Path | None = None
        key_path: Path | None = None
        mkcert_root_ca: Path | None = None
        if not args.skip_certs:
            h = ms.start("Generate TLS certs (mkcert) with CP+DP SANs")
            cert_path, key_path, mkcert_root_ca = _ensure_tls_certs(settings)
            ms.done(h, detail=f"cert={cert_path} key={key_path}")
        else:
            ms.skip("Generate TLS certs (mkcert) with CP+DP SANs", reason="--skip-certs set")
            # Still need root CA for cluster volume mount + secret if we create clusters/secrets.
            mkcert_root_ca = _mkcert_caroot(_mkcert_path())
            cert_dir = Path.home() / ".local" / "share" / "astronomer-software" / "certs"
            cert_path = cert_dir / "astronomer-tls.pem"
            key_path = cert_dir / "astronomer-tls.key"

        if mkcert_root_ca is None:
            raise RuntimeError("mkcert root CA path not available")

        # Step: clusters
        if not args.skip_clusters:
            h = ms.start(f"Ensure k3d clusters exist (CP={settings.clusters.cp}, DP={settings.clusters.dp})")
            if args.recreate_clusters:
                _delete_k3d_cluster(settings.clusters.cp)
                _delete_k3d_cluster(settings.clusters.dp)

            if not _k3d_cluster_exists(settings.clusters.cp):
                _k3d_create_cluster(
                    name=settings.clusters.cp,
                    docker_network=settings.docker_network,
                    ports=[
                        f"{settings.ports.cp_https}:443@loadbalancer",
                        f"{settings.ports.cp_http}:80@loadbalancer",
                    ],
                    mkcert_root_ca=mkcert_root_ca,
                )
            else:
                _debug(f"Cluster already exists, skipping: {settings.clusters.cp}")

            if not _k3d_cluster_exists(settings.clusters.dp):
                _k3d_create_cluster(
                    name=settings.clusters.dp,
                    docker_network=settings.docker_network,
                    ports=[
                        f"{settings.ports.dp_https}:443@loadbalancer",
                        f"{settings.ports.dp_http}:80@loadbalancer",
                    ],
                    mkcert_root_ca=mkcert_root_ca,
                )
            else:
                _debug(f"Cluster already exists, skipping: {settings.clusters.dp}")
            ms.done(h)
        else:
            ms.skip(
                f"Ensure k3d clusters exist (CP={settings.clusters.cp}, DP={settings.clusters.dp})",
                reason="--skip-clusters set",
            )

        cp_context = f"k3d-{settings.clusters.cp}"
        dp_context = f"k3d-{settings.clusters.dp}"

        # Step: namespace + secrets
        if not args.skip_secrets:
            h = ms.start(f"Apply namespace + secrets in both clusters (ns={settings.namespace})")
            if cert_path is None or key_path is None:
                raise RuntimeError("TLS cert/key paths not available; cannot create secrets")

            for ctx in [cp_context, dp_context]:
                _kubectl_create_namespace(ctx, settings.namespace)
                _kubectl_apply_tls_secret(
                    context=ctx,
                    namespace=settings.namespace,
                    secret_name=settings.tls_secret_name,
                    cert_path=cert_path,
                    key_path=key_path,
                )
                _kubectl_apply_generic_secret_from_file(
                    context=ctx,
                    namespace=settings.namespace,
                    secret_name=settings.mkcert_root_ca_secret_name,
                    key=settings.mkcert_root_ca_secret_key,
                    file_path=mkcert_root_ca,
                )
            ms.done(h, detail=f"tlsSecret={settings.tls_secret_name} caSecret={settings.mkcert_root_ca_secret_name}")
        else:
            ms.skip("Apply namespace + secrets in both clusters", reason="--skip-secrets set")

        # Step: values files
        h = ms.start("Write CP/DP Helm values files")
        values_dir: Path
        if args.values_dir:
            values_dir = Path(args.values_dir)
            values_dir.mkdir(parents=True, exist_ok=True)
        else:
            values_dir = Path(tempfile.mkdtemp(prefix="astro-k3d-"))

        cp_values = values_dir / "cp-values.yaml"
        dp_values = values_dir / "dp-values.yaml"
        _write_values_file(cp_values, _cp_values_yaml(settings))
        _write_values_file(dp_values, _dp_values_yaml(settings))
        ms.done(h, detail=f"dir={values_dir}")

        # Step: helm installs
        if not args.skip_helm:
            if args.helm_deps_update:
                h = ms.start("Helm dependency update")
                _helm_dependency_update(Path(GIT_ROOT_DIR))
                ms.done(h)
            else:
                ms.skip("Helm dependency update", reason="Disabled by default (vendored local charts)")

            h = ms.start(f"Helm install/upgrade Control Plane (context={cp_context})")
            _helm_upgrade_install(
                context=cp_context,
                chart_dir=Path(GIT_ROOT_DIR),
                release_name=settings.release_name,
                namespace=settings.namespace,
                values_file=cp_values,
                timeout=settings.helm_timeout,
                debug=settings.helm_debug,
            )
            ms.done(h)

            # IMPORTANT: DP components may need to resolve CP endpoints during startup.
            # Patch DP CoreDNS NodeHosts (and restart CoreDNS) after CP install, before DP install.
            if not args.skip_dns_reconcile:
                h = ms.start("Pre-DP: update DP CoreDNS NodeHosts for CP ingress")
                _run_dns_reconcile(settings)
                ms.done(h)
            else:
                ms.skip("Pre-DP: update DP CoreDNS NodeHosts for CP ingress", reason="--skip-dns-reconcile set")

            h = ms.start(f"Helm install/upgrade Data Plane (context={dp_context})")
            _helm_upgrade_install(
                context=dp_context,
                chart_dir=Path(GIT_ROOT_DIR),
                release_name=settings.release_name,
                namespace=settings.namespace,
                values_file=dp_values,
                timeout=settings.helm_timeout,
                debug=settings.helm_debug,
            )
            ms.done(h)
        else:
            ms.skip("Helm dependency update + CP/DP install", reason="--skip-helm set")

        # Step: DNS reconcile
        if not args.skip_dns_reconcile:
            h = ms.start("Reconcile cross-cluster DNS + node-level hosts pins")
            _run_dns_reconcile(settings)
            ms.done(h)
        else:
            ms.skip("Reconcile cross-cluster DNS + node-level hosts pins", reason="--skip-dns-reconcile set")

        # Step: DP node-level houston.<baseDomain> pin (node-level DNS for kubelet/containerd-like operations)
        if not args.skip_node_registry_check:
            h = ms.start("DP node: pin houston.<baseDomain> to CP ingress (node /etc/hosts)")
            _ensure_dp_node_houston_hosts_pin(settings)
            ms.done(h)
        else:
            ms.skip(
                "DP node: pin houston.<baseDomain> to CP ingress (node /etc/hosts)",
                reason="--skip-node-registry-check set",
            )

        ms.print_summary_table()
        _print_host_etc_hosts_instructions(settings)
        _print("\n✅ Completed.")
        return 0
    except Exception as e:  # noqa: BLE001
        ms.fail_active_if_any(error=str(e))
        ms.print_summary_table()
        _print(f"\n❌ Failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

