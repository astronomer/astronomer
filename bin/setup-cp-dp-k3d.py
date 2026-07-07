#!/usr/bin/env python3
"""
One-shot local CP/DP setup for Astronomer using k3d clusters.

This script automates the workflow documented in `docs/cp-dp-k3d-setup-guide.md`:
- Generate TLS certs (mkcert) with the right SANs for CP + DP subdomains
- Create two k3d clusters on the same Docker network
- Create namespaces + secrets (TLS + mkcert root CA) in both clusters
- Install Astronomer chart into both clusters (CP: unified, DP: data)
- Reconcile cross-cluster DNS + node-level hosts (OrbStack-friendly) using existing helper
- Configure local DNS + a host-level SNI reverse proxy so CP/DP are reachable at
  `https://<sub>.<base-domain>` with no host `/etc/hosts` editing
- Optionally install the Airflow operator (CRDs, cert-manager, ServiceMonitor CRD) on both planes

Notes / constraints:
- We do NOT modify the local machine's `/etc/hosts`. CP/DP each publish a distinct host port for
  their k3d LoadBalancer's :443; a local dnsmasq container resolves `*.<base-domain>` to
  127.0.0.1 (via a one-time `/etc/resolver/<base-domain>` file) and an nginx SNI-passthrough proxy
  on host :443 forwards each hostname to the right cluster's published port. This works
  regardless of Docker Desktop vs OrbStack and isn't affected by container-IP drift.
- We do NOT install k3d/helm/kubectl/mkcert for you by default; we validate and fail with actionable messages.
- Safe to re-run: cluster/secrets/helm installs are done in an idempotent way.

Shared boilerplate (Milestones, docker/k3d, registry proxy, mkcert, cert-manager, kubectl secret
helpers) lives in bin/k3d_setup_shared.py, alongside bin/setup-037x-k3d.py.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from k3d_setup_shared import (
    CERT_MANAGER_VERSION,
    HELM_CHART,
    HELM_REPO_NAME,
    HELM_REPO_URL,
    HELPER_DIR,
    CommandError,
    Milestones,
    _debug,
    _delete_k3d_cluster,
    _docker_inspect_ip,
    _ensure_docker_network,
    _ensure_helm_repo,
    _ensure_local_registries,
    _generate_tls_cert,
    _get_registry_config_path,
    _install_cert_manager,
    _k3d_cluster_exists,
    _k3d_create_cluster,
    _kubectl_apply_generic_secret_from_file,
    _kubectl_apply_tls_secret,
    _kubectl_apply_yaml,
    _kubectl_create_namespace,
    _mkcert_caroot,
    _mkcert_path,
    _pin_cert_manager_to_control_plane,
    _print,
    _require_executable,
    _run,
    _validate_prereqs,
    _wait_for_cert_manager,
)

GIT_ROOT_DIR = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]))

# ---------------------------------------------------------------------------
# Local networking (dnsmasq + SNI reverse proxy) — replaces manual host /etc/hosts editing.
#   - dnsmasq resolves the whole <base-domain> -> 127.0.0.1 (macOS routes it via /etc/resolver).
#   - an nginx SNI-passthrough proxy on host :443 forwards each connection, by TLS server name,
#     to the right cluster's *published host port* (each CP/DP already publishes its own :443
#     to a distinct host port at cluster-creation time — see `_k3d_create_cluster`).
# ---------------------------------------------------------------------------
LOCAL_DNS_PORT = 15354
DNSMASQ_CONF_PATH = HELPER_DIR / "cp-dp-dnsmasq.conf"
DNSMASQ_CONTAINER_NAME = "astro-cp-dp-dnsmasq"
DNSMASQ_IMAGE = "alpine:3.20"

PROXY_CONTAINER_NAME = "astro-cp-dp-proxy"
PROXY_CONF_PATH = HELPER_DIR / "cp-dp-proxy-nginx.conf"
PROXY_IMAGE = "nginx:stable-alpine"  # official nginx; includes the stream + ssl_preread modules

# ServiceMonitor CRD: the airflow-operator's apiserver controller watches monitoring.coreos.com/v1
# ServiceMonitor (an optional Prometheus Operator type). Without the CRD the controller's cache
# fails to sync. We install just the CRD (not the full Prometheus Operator) so the watch succeeds.
PROMETHEUS_OPERATOR_VERSION = "v0.76.0"
SERVICE_MONITOR_CRD_URL = (
    f"https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/{PROMETHEUS_OPERATOR_VERSION}"
    "/example/prometheus-operator-crd/monitoring.coreos.com_servicemonitors.yaml"
)


def _install_service_monitor_crd(context: str) -> None:
    """Server-side apply just the ServiceMonitor CRD so the operator's apiserver watch can sync."""
    _print(f"Applying ServiceMonitor CRD ({PROMETHEUS_OPERATOR_VERSION}) into {context}")
    _run(
        ["kubectl", "--context", context, "apply", "--server-side", "-f", SERVICE_MONITOR_CRD_URL],
        capture=False,
    )


# Friendly `--version` aliases (shown in the interactive picker and accepted on the CLI).
#
# Numbered aliases resolve to a published chart version on HELM_REPO_URL, including
# prereleases (most release-branch versions are only ever published as `-betaN` / timestamped
# CI builds — see `_resolve_chart_version`). "main" is special: it installs from whatever chart
# is currently checked out locally (no version pull) with dev image tags floated in. "0.37" is
# also special: 0.37.x has no CP/DP split (see bin/setup-037x-k3d.py), so main() delegates the
# whole run to that script before any CP/DP settings are built.
VERSION_ALIASES: tuple[str, ...] = ("0.37", "1.1.x", "1.2.x", "2.0.0", "2.0.1", "2.1", "main")
DELEGATE_037_ALIAS = "0.37"
MAIN_DEV_ALIAS = "main"

# `main` floats these first-party image tags to their unreleased branch tag instead of whatever
# the locally checked-out chart pins by default. Houston's API and worker deployments share a
# single `images.houston.tag` knob, so one override covers both (and so does the db-migrations
# job, which runs off the same houston image). `ap-registry` / `ap-vector` are vendored/upstream-
# tracking images with no "main" build, so they are left at chart defaults.
#
# NOTE: `charts/astronomer` is installed as a named subchart ("astronomer") of the root umbrella
# chart, so overrides must be scoped under `astronomer.` — bare `images.houston.tag=...` sets an
# unused top-level key on the umbrella chart and silently no-ops (verified via `helm template`).
MAIN_DEV_IMAGE_SET: tuple[str, ...] = (
    "astronomer.images.houston.tag=main",
    "astronomer.images.astroUI.tag=main",
    "astronomer.images.commander.tag=master",
)

# Friendly topology labels for the interactive picker, mapped to the actual `global.plane.mode`
# value the CP is installed with (see docs/architecture.md). "cp/dp" -> "control" because the DP
# cluster(s) (from --dp-count) always install in `data` mode regardless of this choice.
TOPOLOGY_CHOICES: tuple[str, ...] = ("unified", "cp/dp")
TOPOLOGY_TO_CP_MODE: dict[str, str] = {"unified": "unified", "cp/dp": "control"}
DEFAULT_TOPOLOGY = "unified"


@dataclass(frozen=True)
class ControlPlane:
    cluster_name: str
    https_port: int
    http_port: int


@dataclass(frozen=True)
class DataPlane:
    cluster_name: str
    domain_prefix: str
    https_port: int
    http_port: int


@dataclass(frozen=True)
class Settings:
    base_domain: str
    namespace: str
    release_name: str
    docker_network: str
    cp_mode: str
    control_planes: tuple[ControlPlane, ...]
    data_planes: tuple[DataPlane, ...]
    tls_secret_name: str
    mkcert_root_ca_secret_name: str
    mkcert_root_ca_secret_key: str
    helm_timeout: str
    helm_debug: bool
    dp_airflow_db: str
    enable_operator: bool
    chart_version: str | None = None
    chart_is_prerelease: bool = False
    extra_helm_set: tuple[str, ...] = ()
    agents: int = 0


def _ts() -> str:
    """Return a compact local timestamp for progress logs."""
    return time.strftime("%H:%M:%S")


def _interactive_available() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _prompt_choice(question: str, options: list[str], *, default: str) -> str:
    """Numbered picker (stdlib only). Returns `default` unmodified outside a TTY (CI/automation)."""
    if not _interactive_available():
        return default
    _print(f"\n{question}")
    for i, opt in enumerate(options, start=1):
        marker = "  (default)" if opt == default else ""
        _print(f"  {i}) {opt}{marker}")
    default_idx = options.index(default) + 1 if default in options else 1
    while True:
        raw = input(f"Select [1-{len(options)}] (default {default_idx}): ").strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        if raw in options:
            return raw
        _print(f"  Invalid choice: {raw!r}")


def _prompt_yes_no(question: str, *, default: bool) -> bool:
    """y/n picker (stdlib only). Returns `default` unmodified outside a TTY (CI/automation)."""
    if not _interactive_available():
        return default
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"{question} {suffix}: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        _print(f"  Please answer y or n (got {raw!r})")


def _helm_search_versions(chart_ref: str) -> list[str]:
    """Return published versions of `chart_ref`, newest first (same order `helm search` uses).

    Includes prereleases (`--devel`): most release-branch versions on the internal repo are only
    ever published as `-betaN` / timestamped CI builds, so a search without `--devel` would miss
    almost every non-final version.
    """
    proc = _run(["helm", "search", "repo", chart_ref, "--versions", "--devel", "-o", "json"], check=True)
    try:
        entries = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Could not parse `helm search repo {chart_ref}` output: {e}") from e
    return [str(e["version"]) for e in entries if "version" in e]


def _resolve_chart_version(alias: str, chart_ref: str) -> str:
    """
    Resolve a friendly `--version` alias to a concrete published chart version.

    - An exact final version (e.g. "2.0.0") matches itself first; failing that, the newest
      prerelease of that exact version (e.g. "2.0.1" -> "2.0.1-beta8"), since some versions never
      get a final release before the next one is cut.
    - A minor-only alias (e.g. "1.1.x", "2.1") matches the newest version under that
      major[.minor] prefix, released or not.
    """
    versions = _helm_search_versions(chart_ref)
    if not versions:
        raise RuntimeError(f"`helm search repo {chart_ref} --versions --devel` returned no versions.")

    if alias in versions:
        return alias
    prereleases = [v for v in versions if v.startswith(f"{alias}-")]
    if prereleases:
        return prereleases[0]  # `helm search` already sorts newest-first

    prefix = alias.removesuffix(".x")
    matches = [v for v in versions if v == prefix or v.startswith(f"{prefix}.")]
    if matches:
        return matches[0]

    raise RuntimeError(
        f"No published chart version matches --version '{alias}' on {chart_ref}. "
        f"Newest available versions: {', '.join(versions[:10])}"
    )


def _tls_cert_paths_by_context(settings: Settings) -> dict[str, tuple[Path, Path]]:
    """Map each k3d context to its own cert/key file paths (no mkcert call — just path computation)."""
    cert_dir = Path.home() / ".local" / "share" / "astronomer-software" / "certs"
    paths: dict[str, tuple[Path, Path]] = {}
    for cp in settings.control_planes:
        paths[f"k3d-{cp.cluster_name}"] = (cert_dir / "astronomer-tls-cp.pem", cert_dir / "astronomer-tls-cp.key")
    for dp in settings.data_planes:
        paths[f"k3d-{dp.cluster_name}"] = (
            cert_dir / f"astronomer-tls-{dp.domain_prefix}.pem",
            cert_dir / f"astronomer-tls-{dp.domain_prefix}.key",
        )
    return paths


def _ensure_tls_certs(settings: Settings) -> tuple[dict[str, tuple[Path, Path]], Path]:
    """
    Generate one TLS cert per plane, each scoped to only that plane's hostnames:
    - CP: <baseDomain>, *.<baseDomain>
    - DP (per data plane): <dpPrefix>.<baseDomain>, *.<dpPrefix>.<baseDomain>

    Why per-plane certs instead of one cert covering everything: dnsmasq must resolve every
    hostname to 127.0.0.1 (OrbStack's host-network port forwarding only bridges 127.0.0.1 to the
    Mac host, not other loopback aliases — distinct-IP-per-plane was tried and doesn't work here).
    With every hostname on the same IP, a browser will reuse (HTTP/2-coalesce) an existing TLS
    connection for a different hostname if that connection's certificate is already valid for it.
    A single cert whose SANs cover both `*.<baseDomain>` and `*.<dpPrefix>.<baseDomain>` — applied
    identically to both the CP and DP clusters — satisfies that check, so a connection opened for
    `app.<baseDomain>` (CP) gets silently reused for `commander.<dpPrefix>.<baseDomain>` (DP) and
    vice versa. But the SNI proxy's routing decision is made once per connection (at the TLS
    handshake), so a coalesced connection stays pinned to whichever backend it first routed to —
    responses appear to randomly swap between CP and DP, or hang when the pinned backend can't
    serve the new request's path at all. Scoping each cert's SANs to only its own plane makes a
    CP connection's certificate invalid for any DP hostname (and vice versa), so the browser is
    forced to open a fresh connection — which the SNI proxy then correctly routes.

    Returns:
        ({k3d context -> (cert_path, key_path)}, mkcert_root_ca_path)
    """
    mkcert_exe = _mkcert_path()
    _require_executable(
        mkcert_exe,
        hint="Install mkcert (or run `python3 bin/install-ci-tools.py` to install the repo-pinned version).",
    )

    cert_dir = Path.home() / ".local" / "share" / "astronomer-software" / "certs"
    cert_dir.mkdir(parents=True, exist_ok=True)
    root_ca = _mkcert_caroot(mkcert_exe)
    base = settings.base_domain

    certs_by_context = _tls_cert_paths_by_context(settings)

    cp_cert_path, cp_key_path = certs_by_context[f"k3d-{settings.control_planes[0].cluster_name}"]
    _generate_tls_cert(
        mkcert_exe=mkcert_exe, cert_path=cp_cert_path, key_path=cp_key_path, root_ca=root_ca, sans=[base, f"*.{base}"]
    )

    for dp in settings.data_planes:
        dp_domain = f"{dp.domain_prefix}.{base}"
        dp_cert_path, dp_key_path = certs_by_context[f"k3d-{dp.cluster_name}"]
        _generate_tls_cert(
            mkcert_exe=mkcert_exe,
            cert_path=dp_cert_path,
            key_path=dp_key_path,
            root_ca=root_ca,
            sans=[dp_domain, f"*.{dp_domain}"],
        )

    return certs_by_context, root_ca


def _write_values_file(path: Path, content: str) -> None:
    path.write_text(content)


def _version_specific_values_file(chart_version: str | None) -> Path:
    """
    Pick the plain, hand-written values file with the `global.*` + `houston.config.deployments.*`
    overrides for this chart version's schema (see configs/local-1x.yaml, configs/local-2x.yaml,
    configs/local-dev.yaml — 1.x and 2.x renamed a bunch of these keys, see
    bin/helm_chart_values_migration_shared.py for the full rename list).

    `chart_version=None` means installing from the local checkout (the `main` alias) — that's
    exactly what configs/local-dev.yaml is for. 0.37.x (major version 0) shares 1.x's shape for
    everything these files set, so it reuses configs/local-1x.yaml too; it isn't actually
    installed through this code path in normal use (`--version 0.37` delegates the whole run to
    bin/setup-037x-k3d.py — see DELEGATE_037_ALIAS), this only matters if `--chart-version` is
    used to force a 0.37.x chart version directly.
    """
    if chart_version is None:
        return GIT_ROOT_DIR / "configs" / "local-dev.yaml"
    major = chart_version.split(".", 1)[0]
    try:
        major_num = int(major)
    except ValueError:
        major_num = 2
    filename = "local-1x.yaml" if major_num <= 1 else "local-2x.yaml"
    return GIT_ROOT_DIR / "configs" / filename


def _cp_values_yaml(settings: Settings) -> str:
    operator_block = "  airflowOperator:\n    enabled: true\n" if settings.enable_operator else ""
    operator_subchart_block = (
        """\
airflow-operator:
  crd:
    create: true
  certManager:
    enabled: true
  resources:
    limits:
      cpu: 250m
      memory: 256Mi
    requests:
      cpu: 100m
      memory: 128Mi
"""
        if settings.enable_operator
        else ""
    )
    return f"""\
global:
  baseDomain: {settings.base_domain}
  plane:
    mode: {settings.cp_mode}
    domainPrefix: ""
  tlsSecret: {settings.tls_secret_name}
  privateCaCerts:
    - {settings.mkcert_root_ca_secret_name}
{operator_block}

tags:
  platform: true
  postgresql: true

astronomer:
  houston:
    config:
      cors:
        allowedOrigins:
          - "https://app.{settings.base_domain}"
          - "https://dev.{settings.base_domain}:5000"

postgresql:
  postgresqlUsername: postgres
  postgresqlPassword: postgres
  service:
    type: NodePort
    nodePort: {CP_POSTGRES_NODEPORT}

{operator_subchart_block}"""


def _dp_values_yaml(settings: Settings, dp: DataPlane) -> str:
    """Generate DP Helm values. Postgres on/off is decided by main() via configs/postgres-*.yaml
    depending on --dp-airflow-db — each DP runs its own database rather than sharing the CP's."""
    global_operator_block = "  airflowOperator:\n    enabled: true\n" if settings.enable_operator else ""
    # The airflow-operator subchart is enabled by `global.airflowOperator.enabled`
    # (see Chart.yaml condition). The values block below is only consumed when
    # that flag is on; we emit it only in that case for clarity.
    operator_subchart_block = (
        """\
airflow-operator:
  crd:
    create: true
  certManager:
    enabled: true
  manager:
    replicas: 1
    # Pin the operator controller (which also serves the admission webhook) to
    # the control-plane node.  The kube-apiserver runs on that same node and
    # reaches webhook pods via its own pod-network (10.42.0.x).  If the
    # controller lands on an agent node (10.42.1.x), the apiserver has to
    # traverse the Flannel VXLAN overlay between Docker containers, which
    # fails with "502 Bad Gateway" in k3d.
    nodeSelector:
      node-role.kubernetes.io/control-plane: "true"
    resources:
      limits:
        cpu: 250m
        memory: 256Mi
      requests:
        cpu: 100m
        memory: 128Mi

"""
        if settings.enable_operator
        else ""
    )
    return f"""\
global:
  baseDomain: {settings.base_domain}
  plane:
    mode: data
    domainPrefix: {dp.domain_prefix}
  tlsSecret: {settings.tls_secret_name}
  privateCaCerts:
    - {settings.mkcert_root_ca_secret_name}
{global_operator_block}
tags:
  platform: true
  postgresql: false

{operator_subchart_block}"""


CP_POSTGRES_NODEPORT = 5432

MYSQL_ROOT_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "rootpassword")
MYSQL_IMAGE = "mysql:8.0"


def _mysql_service_name(release_name: str) -> str:
    """Return the Kubernetes Service name for the MySQL instance."""
    return f"{release_name}-mysql"


MYSQL_MANIFEST_TEMPLATE = GIT_ROOT_DIR / "configs" / "mysql-manifest.yaml"


def _mysql_manifest_yaml(namespace: str, release_name: str) -> str:
    """Fill in configs/mysql-manifest.yaml for a local MySQL 8.0 Deployment + Service."""
    svc_name = _mysql_service_name(release_name)
    return MYSQL_MANIFEST_TEMPLATE.read_text().format(
        svc_name=svc_name,
        namespace=namespace,
        labels=f"app: {svc_name}",
        mysql_image=MYSQL_IMAGE,
        mysql_root_password=MYSQL_ROOT_PASSWORD,
    )


def _deploy_mysql(*, context: str, namespace: str, release_name: str) -> None:
    """Deploy MySQL into the cluster and wait for it to become ready."""
    manifest = _mysql_manifest_yaml(namespace, release_name)
    _kubectl_apply_yaml(context, manifest)

    svc_name = _mysql_service_name(release_name)
    _print(f"Waiting for MySQL pod to become ready ({svc_name})")
    _run(
        [
            "kubectl",
            "--context",
            context,
            "-n",
            namespace,
            "wait",
            "--for=condition=available",
            f"deployment/{svc_name}",
            "--timeout=180s",
        ],
        check=True,
    )


def _create_astronomer_bootstrap_secret_mysql(*, context: str, namespace: str, release_name: str) -> None:
    """Create (or update) the astronomer-bootstrap secret with a MySQL connection string."""
    svc_name = _mysql_service_name(release_name)
    conn = f"mysql://root:{MYSQL_ROOT_PASSWORD}@{svc_name}.{namespace}.svc.cluster.local:3306"

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
            "astronomer-bootstrap",
            f"--from-literal=connection={conn}",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
        check=True,
    ).stdout
    _kubectl_apply_yaml(context, secret_yaml)
    _debug(f"astronomer-bootstrap secret set with MySQL connection: {svc_name}")


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
    chart_version: str | None = None,
    chart_is_prerelease: bool = False,
    extra_set: tuple[str, ...] = (),
    base_values_files: tuple[Path, ...] = (),
) -> None:
    """
    `base_values_files` are applied BEFORE `values_file` (lowest precedence — e.g. the plain
    version-specific overrides in configs/local-*.yaml), so `values_file` (this script's
    per-invocation settings, like CP-vs-DP postgres enable/disable) always wins over them.
    `extra_values_files` (e.g. --helm-values) are applied last and win over everything.
    """
    chart_ref = HELM_CHART if chart_version else str(chart_dir)
    cmd = [
        "helm",
        "upgrade",
        "--install",
        release_name,
        chart_ref,
        "--namespace",
        namespace,
        "--kube-context",
        context,
    ]
    for base in base_values_files:
        cmd.extend(["--values", str(base)])
    cmd.extend(
        [
            "--values",
            str(values_file),
            "--timeout",
            timeout,
            "--wait",
        ]
    )
    if chart_version:
        cmd.extend(["--version", chart_version])
        if chart_is_prerelease:
            cmd.append("--devel")
    for extra in extra_values_files:
        cmd.extend(["--values", str(extra)])
    for s in extra_set:
        cmd.extend(["--set", s])
    if debug:
        cmd.append("--debug")
    _print(f"Helm upgrade/install ({context}): {release_name} in ns={namespace}")
    _run(cmd, check=True, capture=False)


def _run_dns_reconcile(settings: Settings, cp: ControlPlane, dp: DataPlane) -> None:
    """
    Run the existing reconcile helper to pin CoreDNS NodeHosts and the DP node's /etc/hosts.
    """
    script = GIT_ROOT_DIR / "bin" / "reconcile-k3d-orbstack-network.py"
    env = dict(os.environ)
    env.update(
        {
            "CP_CONTEXT": f"k3d-{cp.cluster_name}",
            "DP_CONTEXT": f"k3d-{dp.cluster_name}",
            "PLATFORM_NAMESPACE": settings.namespace,
            "BASE_DOMAIN": settings.base_domain,
            "DP_DOMAIN_PREFIX": dp.domain_prefix,
            "DP_NODE_CONTAINER": f"k3d-{dp.cluster_name}-server-0",
            "DP_AGENTS": str(settings.agents),
            "CP_INGRESS_SERVICE": f"{settings.release_name}-cp-nginx",
        }
    )
    _print(f"Reconciling k3d cross-cluster DNS + node-level hosts pins (DP={dp.cluster_name})")
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


def _ensure_dp_node_houston_hosts_pin(settings: Settings, dp: DataPlane) -> None:
    """
    Ensure all DP node containers (server + agents) have node-level DNS pin for
    `houston.<baseDomain>` -> CP ingress LB IP.

    Why:
    - Pods resolve via CoreDNS, but node-level operations (kubelet/containerd image pulls) use node DNS + /etc/hosts.
    - If `houston.<baseDomain>` resolves incorrectly at the node level, registry auth can break.
    - With agent nodes, pods can be scheduled on any node, so all nodes need the pin.
    """
    primary_cp = settings.control_planes[0]
    cp_context = f"k3d-{primary_cp.cluster_name}"
    cp_nginx_svc = f"{settings.release_name}-cp-nginx"

    cp_nginx_lb_ip = _kubectl_get_service_lb_ip(cp_context, settings.namespace, cp_nginx_svc)
    houston_host = f"houston.{settings.base_domain}"

    # Patch server node
    node_containers = [f"k3d-{dp.cluster_name}-server-0"]
    # Patch all agent nodes
    node_containers += [f"k3d-{dp.cluster_name}-agent-{i}" for i in range(settings.agents)]

    for container in node_containers:
        _ensure_container_hosts_mapping(container, cp_nginx_lb_ip, houston_host)
        _debug(f"Ensured /etc/hosts pin on {container}: {cp_nginx_lb_ip} {houston_host}")


def _print_manual_etc_hosts_fallback(settings: Settings) -> None:
    """
    Fallback ONLY: print /etc/hosts entries pointing at the k3d `*-serverlb` container IPs.

    Used when `_setup_local_networking` itself fails (e.g. can't bind :443, no sudo for
    /etc/resolver). These IPs are only host-routable under OrbStack and can drift on
    container restart, which is exactly why `_setup_local_networking` exists — prefer that path.
    """
    base = settings.base_domain

    _print("\nCould not configure local DNS + proxy automatically. As a fallback, add these entries to your host `/etc/hosts`:\n")
    for dp in settings.data_planes:
        dp_serverlb = f"k3d-{dp.cluster_name}-serverlb"
        dp_nginx_lb_ip = _docker_inspect_ip(dp_serverlb)
        prefix = dp.domain_prefix
        _print(
            f"{dp_nginx_lb_ip} {prefix}.{base} deployments.{prefix}.{base} registry.{prefix}.{base} commander.{prefix}.{base} prometheus.{prefix}.{base} prom-proxy.{prefix}.{base} elasticsearch.{prefix}.{base}"
        )
    for cp in settings.control_planes:
        cp_serverlb = f"k3d-{cp.cluster_name}-serverlb"
        cp_nginx_lb_ip = _docker_inspect_ip(cp_serverlb)
        _print(
            f"{cp_nginx_lb_ip} {base} app.{base} houston.{base} grafana.{base} prometheus.{base} elasticsearch.{base} alertmanager.{base} registry.{base}"
        )


def _resolver_file_path(base_domain: str) -> Path:
    return Path("/etc/resolver") / base_domain


def _write_dnsmasq_conf(base_domain: str) -> None:
    """Write the dnsmasq config: resolve the whole base domain to 127.0.0.1 (the SNI proxy).

    Mounted into the dnsmasq container, which listens inside the container (all interfaces) on
    port 53 — Docker DNATs the published 127.0.0.1:LOCAL_DNS_PORT to it. Routing to the correct
    cluster happens at the nginx proxy by SNI, so DNS only needs a single 127.0.0.1 answer.

    NOTE: giving each plane its own 127.0.0.x loopback IP was tried (to stop browsers from
    HTTP/2-coalescing CP and DP connections) and reverted — OrbStack's host-network port
    forwarding only bridges 127.0.0.1 to the Mac host, not other loopback aliases, even with an
    explicit `-p 127.0.0.2:PORT:PORT` publish. The coalescing fix instead lives in
    `_ensure_tls_certs`: each plane gets its own cert whose SANs don't cover the other plane's
    hostnames, which is what actually gates HTTP/2 connection reuse.
    """
    lines = [
        "# Managed by bin/setup-cp-dp-k3d.py — regenerated each run. Do not edit by hand.",
        "port=53",  # in-container port; published to the host as 127.0.0.1:LOCAL_DNS_PORT
        "no-resolv",  # only answer for our domain; never act as a general resolver
        "no-hosts",
        "local-ttl=0",
        # Authoritative for our domain. The address= record is IPv4-only, but macOS fires an AAAA
        # query alongside the A query; without this, dnsmasq gives no clean AAAA answer and the
        # resolver stalls ~5s before falling back to the A record. `local=` makes dnsmasq answer
        # AAAA authoritatively (immediate NODATA), removing the delay.
        f"local=/{base_domain}/",
        f"address=/{base_domain}/127.0.0.1",
    ]
    HELPER_DIR.mkdir(parents=True, exist_ok=True)
    DNSMASQ_CONF_PATH.write_text("\n".join(lines) + "\n")


def _ensure_dnsmasq_container() -> None:
    """(Re)create the dnsmasq container from the freshly-written config.

    Recreated (not just restarted) each run so the current config takes effect. Uses the official
    Alpine image and installs dnsmasq at start, avoiding a third-party image.
    `--restart unless-stopped` keeps it answering across OrbStack/Docker restarts.
    """
    _run(["docker", "rm", "-f", DNSMASQ_CONTAINER_NAME], check=False, capture=True)
    _run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            DNSMASQ_CONTAINER_NAME,
            "--restart",
            "unless-stopped",
            "-p",
            f"127.0.0.1:{LOCAL_DNS_PORT}:53/udp",
            "-p",
            f"127.0.0.1:{LOCAL_DNS_PORT}:53/tcp",
            "-v",
            f"{DNSMASQ_CONF_PATH}:/etc/dnsmasq.conf:ro",
            "--entrypoint",
            "sh",
            DNSMASQ_IMAGE,
            "-c",
            "apk add --no-cache dnsmasq >/dev/null && exec dnsmasq -k --conf-file=/etc/dnsmasq.conf",
        ],
        check=True,
    )
    for _ in range(600):  # ~5min — `apk add` is a fresh network fetch every run, slower under load
        if _run(["docker", "exec", DNSMASQ_CONTAINER_NAME, "pidof", "dnsmasq"], check=False).returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError(f"dnsmasq container {DNSMASQ_CONTAINER_NAME} did not start; check `docker logs {DNSMASQ_CONTAINER_NAME}`")


def _write_proxy_conf(*, base_domain: str, dp_entries: list[tuple[str, int]], cp_port: int) -> None:
    """Write the nginx stream config: route each TLS connection by SNI to a cluster's host port.

    `dp_entries` is one (domain_prefix, https_port) pair per data plane. Everything under
    <base_domain> that doesn't match a DP prefix (houston, app, the bare domain, ...) goes to the
    CP port. ssl_preread reads the TLS SNI without terminating TLS, so no certs live at the proxy
    — the k3d ingress still does TLS.
    """
    map_lines = []
    for prefix, port in dp_entries:
        suffix = f"{prefix}.{base_domain}".replace(".", "\\.")
        map_lines.append(f"        ~*(^|\\.){suffix}$   127.0.0.1:{port};   # *.{prefix}.{base_domain} -> DP {prefix}")
    maps_block = "\n".join(map_lines)
    conf = f"""\
# Managed by bin/setup-cp-dp-k3d.py — regenerated each run. Do not edit by hand.
worker_processes 1;
events {{}}
stream {{
    map $ssl_preread_server_name $apc_upstream {{
{maps_block}
        default                 127.0.0.1:{cp_port};   # everything else under {base_domain} -> CP
    }}
    server {{
        listen 443;
        ssl_preread on;
        proxy_pass $apc_upstream;
    }}
}}
"""
    HELPER_DIR.mkdir(parents=True, exist_ok=True)
    PROXY_CONF_PATH.write_text(conf)


def _ensure_proxy_container() -> None:
    """(Re)create the SNI reverse-proxy container from the freshly-written config.

    Host networking: binds the host's :443 and reaches the k3d serverlb published ports at
    127.0.0.1:<port>. Recreated each run so new cluster ports apply.
    """
    _run(["docker", "rm", "-f", PROXY_CONTAINER_NAME], check=False, capture=True)
    _run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            PROXY_CONTAINER_NAME,
            "--restart",
            "unless-stopped",
            "--network",
            "host",
            "-v",
            f"{PROXY_CONF_PATH}:/etc/nginx/nginx.conf:ro",
            PROXY_IMAGE,
        ],
        check=True,
    )
    for _ in range(20):  # ~10s
        if _run(["docker", "exec", PROXY_CONTAINER_NAME, "pidof", "nginx"], check=False).returncode == 0:
            return
        time.sleep(0.5)
    raise RuntimeError(f"proxy container {PROXY_CONTAINER_NAME} did not start; check `docker logs {PROXY_CONTAINER_NAME}`")


def _ensure_resolver_file(base_domain: str) -> bool:
    """Ensure /etc/resolver/<base_domain> routes the domain to our dnsmasq. Returns True if changed.

    Needs sudo, but only when the file is missing or wrong (first run) — re-runs are prompt-free.
    """
    want = f"nameserver 127.0.0.1\nport {LOCAL_DNS_PORT}\n"
    path = _resolver_file_path(base_domain)
    try:
        if path.read_text() == want:
            return False
    except OSError:
        pass
    _print(f"  Writing {path} (needs sudo, one-time)")
    _run(["sudo", "mkdir", "-p", "/etc/resolver"], check=True)
    _run(["sudo", "tee", str(path)], stdin=want, check=True)
    return True


def _verify_local_networking(base_domain: str, hosts: list[str]) -> None:
    """Best-effort end-to-end check: name -> 127.0.0.1 (dnsmasq) -> :443 proxy -> right cluster."""
    for host in hosts:
        dns = _run(["dscacheutil", "-q", "host", "-a", "name", host], check=False)
        ips = [ln.split(":", 1)[1].strip() for ln in (dns.stdout or "").splitlines() if ln.startswith("ip_address")]
        dns_ok = "127.0.0.1" in ips
        curl = _run(
            ["curl", "-sk", "--max-time", "4", "-o", "/dev/null", "-w", "%{http_code}", f"https://{host}/"],
            check=False,
        )
        code = (curl.stdout or "").strip()
        reachable = code.isdigit() and code != "000"
        marker = "[ok]" if (dns_ok and reachable) else "[FAILED]"
        _print(f"    {host} -> DNS {', '.join(ips) or 'none'}, proxy HTTP {code or 'none'} {marker}")


def _setup_local_networking(settings: Settings) -> str:
    """Configure local DNS + SNI reverse proxy for CP/DP ingress (replaces manual /etc/hosts edits).

    dnsmasq resolves *.<base> -> 127.0.0.1; an nginx SNI proxy on :443 forwards each hostname to
    the right cluster's already-known published host port (`ControlPlane.https_port` /
    `DataPlane.https_port`, fixed at cluster-creation time — no container-IP lookup needed).
    Raises on failure; the caller falls back to `_print_manual_etc_hosts_fallback` so a dev is
    never fully blocked.
    """
    base = settings.base_domain
    primary_cp = settings.control_planes[0]
    dp_entries = [(dp.domain_prefix, dp.https_port) for dp in settings.data_planes]

    _write_dnsmasq_conf(base)
    _ensure_dnsmasq_container()
    changed = _ensure_resolver_file(base)

    _write_proxy_conf(base_domain=base, dp_entries=dp_entries, cp_port=primary_cp.https_port)
    _ensure_proxy_container()

    _print(f"  dnsmasq `{DNSMASQ_CONTAINER_NAME}`: *.{base} -> 127.0.0.1 (127.0.0.1:{LOCAL_DNS_PORT})")
    dp_summary = ", ".join(f"{prefix}->:{port}" for prefix, port in dp_entries) or "<none>"
    _print(f"  proxy `{PROXY_CONTAINER_NAME}` on :443 by SNI: {dp_summary} (DP), else -> :{primary_cp.https_port} (CP)")

    check_hosts = [f"houston.{base}"] + [f"commander.{prefix}.{base}" for prefix, _ in dp_entries]
    _verify_local_networking(base, check_hosts)
    return f"resolver {'created' if changed else 'present'}; proxy CP:{primary_cp.https_port} DP:{[p for _, p in dp_entries]}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automate Astronomer CP/DP local setup using k3d.")
    parser.add_argument("--base-domain", default="localtest.me")
    parser.add_argument("--namespace", default="astronomer")
    parser.add_argument("--release-name", default="astronomer")
    parser.add_argument("--docker-network", default="astronomer-net")
    parser.add_argument(
        "--cp-count",
        type=int,
        default=1,
        choices=range(1, 2),
        help="Number of control plane clusters to create. Clusters are named cp01, cp02, … Default: '%(default)s'",
    )
    parser.add_argument(
        "--dp-count",
        type=int,
        default=1,
        choices=range(1, 5),
        help="Number of data plane clusters to create. Clusters are named dp01, dp02, … Default: '%(default)s'",
    )

    parser.add_argument(
        "--cp-mode",
        type=str,
        default=None,
        help=(
            "Control plane mode to install: 'unified' (single cluster, CP+DP co-located) or "
            "'control' (true CP/DP split, paired with the DP cluster(s) from --dp-count). "
            "Omit to be prompted interactively; falls back to 'unified' outside a TTY."
        ),
    )
    parser.add_argument(
        "--cp-base-https-port",
        type=int,
        default=8443,
        help="Base HTTPS port for the first control plane; subsequent control planes increment by 1. Default: '%(default)s'",
    )
    parser.add_argument(
        "--cp-base-http-port",
        type=int,
        default=8080,
        help="Base HTTP port for the first control plane; subsequent control planes increment by 1. Default: '%(default)s'",
    )
    parser.add_argument(
        "--dp-base-https-port",
        type=int,
        default=None,
        help="Base HTTPS port for the first data plane; subsequent data planes increment by 1. Defaults to --cp-base-https-port + cp-count.",
    )
    parser.add_argument(
        "--dp-base-http-port",
        type=int,
        default=None,
        help="Base HTTP port for the first data plane; subsequent data planes increment by 1. Defaults to --cp-base-http-port + cp-count.",
    )

    parser.add_argument("--tls-secret-name", default="astronomer-tls")
    parser.add_argument("--mkcert-root-ca-secret-name", default="mkcert-root-ca")
    parser.add_argument("--mkcert-root-ca-secret-key", default="cert.pem")

    version_group = parser.add_mutually_exclusive_group()
    version_group.add_argument(
        "--version",
        dest="version_alias",
        default=None,
        metavar="ALIAS",
        help=(
            "Friendly Astronomer version to install: one of "
            f"{', '.join(VERSION_ALIASES)}, or any exact/partial chart version known to "
            f"{HELM_REPO_URL} (e.g. '1.1.4'). "
            "'0.37' has no CP/DP split and delegates this entire run to bin/setup-037x-k3d.py. "
            "'main' installs from the locally checked-out chart and floats "
            "houston/astroUI/dbBootstrapper to the 'main' image tag and commander to 'master'. "
            f"Omit to be prompted interactively; falls back to '{MAIN_DEV_ALIAS}' outside a TTY."
        ),
    )
    version_group.add_argument(
        "--chart-version",
        default=None,
        metavar="VERSION",
        help=(
            "Exact Astronomer chart version to install from the remote Helm repo "
            f"({HELM_REPO_URL}), e.g. '1.2.3-beta1'. Bypasses --version alias resolution "
            "(including the 0.37 delegation and the 'main' dev-image overrides)."
        ),
    )

    parser.add_argument("--helm-timeout", default=os.environ.get("HELM_TIMEOUT", "60m"))
    parser.add_argument("--helm-debug", action="store_true")
    parser.add_argument(
        "--helm-deps-update",
        action="store_true",
        help="Run `helm dependency update` before installing (off by default; local charts are already vendored).",
    )

    parser.add_argument("--recreate-clusters", action="store_true", help="Delete and recreate k3d clusters if they exist")
    parser.add_argument(
        "--num-compute-nodes",
        dest="num_compute_nodes",
        type=int,
        default=0,
        help="Number of additional k3d worker nodes per cluster (mapped to k3d --agents). Applies to both CP and DP clusters. Default: %(default)s. Prefer allocating more CPU/memory in Docker Desktop over adding nodes.",
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
        "--skip-local-networking",
        action="store_true",
        help=(
            "Skip the local dnsmasq + SNI-proxy setup (host :443, /etc/resolver) and print manual /etc/hosts instructions instead."
        ),
    )

    parser.add_argument(
        "--values-dir",
        default="",
        help="Directory to write cp-values.yaml + dp-<name>-values.yaml files. Defaults to a temp directory.",
    )

    parser.add_argument(
        "--helm-values",
        action="append",
        default=[],
        dest="helm_values",
        metavar="FILE",
        help="Extra Helm values file passed to both CP and DP installs (can be repeated).",
    )

    parser.add_argument(
        "--dp-airflow-db",
        choices=["postgres", "mysql"],
        default=None,
        help=(
            "Database type for Airflow deployments on the data plane. "
            "Omit to be prompted interactively; falls back to 'postgres' outside a TTY."
        ),
    )

    parser.add_argument(
        "--enable-operator",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Enable Airflow operator mode. Sets global.airflowOperator.enabled=true on "
            "both CP and DP, and renders the airflow-operator subchart values on the DP. "
            "Pass --no-enable-operator to fall back to the helm-based airflow path. "
            "Omit to be prompted interactively; falls back to enabled outside a TTY."
        ),
    )
    parser.add_argument(
        "--skip-service-monitor-crd",
        action="store_true",
        help=(
            "When --enable-operator is set, skip installing the ServiceMonitor CRD "
            "(monitoring.coreos.com/v1). The operator's apiserver controller watches ServiceMonitor "
            "and its cache fails to sync without the CRD; pass this only if a full Prometheus "
            "Operator (or the CRD) is already installed in the cluster."
        ),
    )

    return parser.parse_args()


class Delegate037(Exception):
    """Raised by `_resolve_version` when --version resolves to "0.37" (no CP/DP split)."""


def _resolve_version(args: argparse.Namespace) -> tuple[str | None, bool, tuple[str, ...]]:
    """
    Resolve --version/--chart-version into (chart_version, chart_is_prerelease, extra_helm_set).

    Raises Delegate037 if the resolved alias is "0.37": the caller must run
    bin/setup-037x-k3d.py instead of continuing with the normal CP/DP flow, since 0.37.x has no
    control/data plane separation.
    """
    if args.chart_version:
        return args.chart_version, "-" in args.chart_version, ()

    alias = args.version_alias
    if alias is None:
        alias = _prompt_choice(
            "Which Astronomer version do you want to install?",
            list(VERSION_ALIASES),
            default=MAIN_DEV_ALIAS,
        )
    if alias == DELEGATE_037_ALIAS:
        raise Delegate037
    if alias == MAIN_DEV_ALIAS:
        return None, False, MAIN_DEV_IMAGE_SET

    _ensure_helm_repo()
    resolved = _resolve_chart_version(alias, HELM_CHART)
    return resolved, "-" in resolved, ()


def _run_setup_037(args: argparse.Namespace) -> int:
    """Delegate the whole run to bin/setup-037x-k3d.py: 0.37.x has no CP/DP split to set up."""
    script = Path(__file__).resolve().parent / "setup-037x-k3d.py"
    cmd = [
        sys.executable,
        str(script),
        "--base-domain",
        args.base_domain,
        "--namespace",
        args.namespace,
        "--release-name",
        args.release_name,
        "--docker-network",
        args.docker_network,
        "--https-port",
        str(args.cp_base_https_port),
        "--http-port",
        str(args.cp_base_http_port),
        "--tls-secret-name",
        args.tls_secret_name,
        "--mkcert-root-ca-secret-name",
        args.mkcert_root_ca_secret_name,
        "--mkcert-root-ca-secret-key",
        args.mkcert_root_ca_secret_key,
        "--helm-timeout",
        args.helm_timeout,
        "--num-compute-nodes",
        str(args.num_compute_nodes),
    ]
    if args.chart_version:
        cmd += ["--chart-version", args.chart_version]
    if args.helm_debug:
        cmd.append("--helm-debug")
    if args.recreate_clusters:
        cmd.append("--recreate-cluster")
    if args.no_local_registry:
        cmd.append("--no-local-registry")
    if args.skip_certs:
        cmd.append("--skip-certs")
    if args.skip_clusters:
        cmd.append("--skip-cluster")
    if args.skip_secrets:
        cmd.append("--skip-secrets")
    if args.skip_helm:
        cmd.append("--skip-helm")
    if args.values_dir:
        cmd += ["--values-dir", args.values_dir]
    for f in args.helm_values:
        cmd += ["--helm-values", f]

    _print("--version 0.37 has no CP/DP split; delegating this run entirely to bin/setup-037x-k3d.py\n")
    _debug(f"run: {shlex.join(cmd)}")
    return subprocess.run(cmd).returncode


def main() -> int:  # noqa: C901
    args = parse_args()

    if GIT_ROOT_DIR is None:
        raise RuntimeError("Could not locate repo root (missing .git).")

    _require_executable("helm", hint="Install helm and ensure it is in PATH.")
    try:
        resolved_chart_version, chart_is_prerelease, extra_helm_set = _resolve_version(args)
    except Delegate037:
        return _run_setup_037(args)
    except (CommandError, RuntimeError) as e:
        _print(f"\n❌ Failed to resolve --version: {e}")
        return 1

    enable_operator = args.enable_operator
    if enable_operator is None:
        enable_operator = _prompt_yes_no("Enable Airflow operator mode?", default=True)

    cp_mode = args.cp_mode
    if cp_mode is None:
        topology = _prompt_choice(
            "Which topology do you want to install?",
            list(TOPOLOGY_CHOICES),
            default=DEFAULT_TOPOLOGY,
        )
        cp_mode = TOPOLOGY_TO_CP_MODE[topology]

    dp_airflow_db = args.dp_airflow_db
    if dp_airflow_db is None:
        dp_airflow_db = _prompt_choice(
            "Which database should data planes use?",
            ["postgres", "mysql"],
            default="postgres",
        )

    ms = Milestones()

    dp_base_https = args.dp_base_https_port if args.dp_base_https_port is not None else (args.cp_base_https_port + args.cp_count)
    dp_base_http = args.dp_base_http_port if args.dp_base_http_port is not None else (args.cp_base_http_port + args.cp_count)

    control_planes = tuple(
        ControlPlane(
            cluster_name=f"cp{i:02d}",
            https_port=args.cp_base_https_port + (i - 1),
            http_port=args.cp_base_http_port + (i - 1),
        )
        for i in range(1, args.cp_count + 1)
    )

    data_planes = tuple(
        DataPlane(
            cluster_name=f"dp{i:02d}",
            domain_prefix=f"dp{i:02d}",
            https_port=dp_base_https + (i - 1),
            http_port=dp_base_http + (i - 1),
        )
        for i in range(1, args.dp_count + 1)
    )

    settings = Settings(
        base_domain=args.base_domain,
        namespace=args.namespace,
        release_name=args.release_name,
        docker_network=args.docker_network,
        cp_mode=cp_mode,
        control_planes=control_planes,
        data_planes=data_planes,
        tls_secret_name=args.tls_secret_name,
        mkcert_root_ca_secret_name=args.mkcert_root_ca_secret_name,
        mkcert_root_ca_secret_key=args.mkcert_root_ca_secret_key,
        helm_timeout=args.helm_timeout,
        helm_debug=bool(args.helm_debug),
        dp_airflow_db=dp_airflow_db,
        enable_operator=enable_operator,
        chart_version=resolved_chart_version,
        chart_is_prerelease=chart_is_prerelease,
        extra_helm_set=extra_helm_set,
        agents=args.num_compute_nodes,
    )

    try:
        h = ms.start("Validate prerequisites (docker/k3d/kubectl/helm)")
        _validate_prereqs()
        ms.done(h)

        # Step: Docker network
        h = ms.start(f"Ensure Docker network `{settings.docker_network}` exists")
        _ensure_docker_network(settings.docker_network)
        ms.done(h)

        # Step: local registry proxies
        registry_config: Path | None = None
        if not args.no_local_registry:
            h = ms.start("Ensure local pull-through registry proxy containers are running")
            _ensure_local_registries(settings.docker_network)
            registry_config = _get_registry_config_path(settings.docker_network)
            ms.done(h, detail=f"config={registry_config}")
        else:
            ms.skip("Local registry proxy setup", reason="--no-local-registry set")

        # Step: TLS + mkcert root CA file
        certs_by_context: dict[str, tuple[Path, Path]] | None = None
        mkcert_root_ca: Path | None = None
        if not args.skip_certs:
            h = ms.start("Generate TLS certs (mkcert) — one per plane, scoped to its own hostnames")
            certs_by_context, mkcert_root_ca = _ensure_tls_certs(settings)
            ms.done(h, detail=f"{len(certs_by_context)} cert(s): {', '.join(sorted(certs_by_context))}")
        else:
            ms.skip("Generate TLS certs (mkcert) — one per plane, scoped to its own hostnames", reason="--skip-certs set")
            # Still need root CA for cluster volume mount + secret if we create clusters/secrets.
            mkcert_root_ca = _mkcert_caroot(_mkcert_path())
            certs_by_context = _tls_cert_paths_by_context(settings)

        if mkcert_root_ca is None:
            raise RuntimeError("mkcert root CA path not available")

        # Step: clusters
        cp_names = ", ".join(cp.cluster_name for cp in settings.control_planes)
        dp_names = ", ".join(dp.cluster_name for dp in settings.data_planes)
        if not args.skip_clusters:
            h = ms.start(f"Ensure k3d clusters exist (CP={cp_names}, DP={dp_names})")
            if args.recreate_clusters:
                for cp in settings.control_planes:
                    _delete_k3d_cluster(cp.cluster_name)
                for dp in settings.data_planes:
                    _delete_k3d_cluster(dp.cluster_name)

            for cp in settings.control_planes:
                if not _k3d_cluster_exists(cp.cluster_name):
                    _k3d_create_cluster(
                        name=cp.cluster_name,
                        docker_network=settings.docker_network,
                        ports=[
                            f"{cp.https_port}:443@loadbalancer",
                            f"{cp.http_port}:80@loadbalancer",
                        ],
                        mkcert_root_ca=mkcert_root_ca,
                        # Expand NodePort range so postgres can be exposed as NodePort 5432.
                        extra_k3s_args=["--kube-apiserver-arg=--service-node-port-range=1024-65535@server:0"],
                        registry_config=registry_config,
                    )
                else:
                    _debug(f"Cluster already exists, skipping: {cp.cluster_name}")

            for dp in settings.data_planes:
                if not _k3d_cluster_exists(dp.cluster_name):
                    _k3d_create_cluster(
                        name=dp.cluster_name,
                        docker_network=settings.docker_network,
                        ports=[
                            f"{dp.https_port}:443@loadbalancer",
                            f"{dp.http_port}:80@loadbalancer",
                        ],
                        mkcert_root_ca=mkcert_root_ca,
                        agents=settings.agents,
                        registry_config=registry_config,
                    )
                else:
                    _debug(f"Cluster already exists, skipping: {dp.cluster_name}")
            ms.done(h)
        else:
            ms.skip(
                f"Ensure k3d clusters exist (CP={cp_names}, DP={dp_names})",
                reason="--skip-clusters set",
            )

        # Step: namespace + secrets
        if not args.skip_secrets:
            h = ms.start(f"Apply namespace + secrets in all clusters (ns={settings.namespace})")
            if certs_by_context is None:
                raise RuntimeError("TLS cert/key paths not available; cannot create secrets")

            for ctx in [f"k3d-{cp.cluster_name}" for cp in settings.control_planes] + [
                f"k3d-{dp.cluster_name}" for dp in settings.data_planes
            ]:
                _kubectl_create_namespace(ctx, settings.namespace)
                cert_path, key_path = certs_by_context[ctx]
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
            ms.skip("Apply namespace + secrets in all clusters", reason="--skip-secrets set")

        # Step: deploy MySQL in DP clusters (when --dp-airflow-db=mysql)
        # Bootstrap secrets (postgres or mysql) are created later in a dedicated step after CP helm install.
        if settings.dp_airflow_db == "mysql":
            for dp in settings.data_planes:
                dp_ctx = f"k3d-{dp.cluster_name}"
                h = ms.start(f"Deploy MySQL in DP cluster ({dp.cluster_name})")
                _deploy_mysql(context=dp_ctx, namespace=settings.namespace, release_name=settings.release_name)
                ms.done(h, detail=f"svc={_mysql_service_name(settings.release_name)}")

        # Step: values files
        h = ms.start("Write CP/DP Helm values files")
        values_dir: Path
        if args.values_dir:
            values_dir = Path(args.values_dir)
            values_dir.mkdir(parents=True, exist_ok=True)
        else:
            values_dir = Path(tempfile.mkdtemp(prefix="astro-k3d-"))

        cp_values_files: dict[str, Path] = {}
        for cp in settings.control_planes:
            cp_values_path = values_dir / f"cp-{cp.cluster_name}-values.yaml"
            _write_values_file(cp_values_path, _cp_values_yaml(settings))
            cp_values_files[cp.cluster_name] = cp_values_path
        dp_values_files: dict[str, Path] = {}
        for dp in settings.data_planes:
            dp_values_path = values_dir / f"dp-{dp.cluster_name}-values.yaml"
            _write_values_file(dp_values_path, _dp_values_yaml(settings, dp))
            dp_values_files[dp.cluster_name] = dp_values_path
        ms.done(h, detail=f"dir={values_dir}")

        # Step: helm installs
        if not args.skip_helm:
            if settings.chart_version:
                h = ms.start(f"Ensure Helm repo `{HELM_REPO_NAME}` is up-to-date")
                _ensure_helm_repo()
                ms.done(h, detail=f"version={settings.chart_version}")
            elif args.helm_deps_update:
                h = ms.start("Helm dependency update")
                _helm_dependency_update(GIT_ROOT_DIR)
                ms.done(h)
            else:
                ms.skip("Helm dependency update", reason="Disabled by default (vendored local charts)")

            for cp in settings.control_planes:
                h = ms.start(f"Helm install/upgrade Control Plane (context=k3d-{cp.cluster_name})")

                cp_ctx = f"k3d-{cp.cluster_name}"

                # The airflow-operator webhooks need cert-manager's Issuer/Certificate
                # flow to produce `webhook-server-cert`. Install cert-manager before the
                # helm release so the Certificate the chart creates can be fulfilled.
                if settings.enable_operator:
                    h = ms.start(f"Install cert-manager on {cp.cluster_name} (operator webhooks)")
                    _install_cert_manager(cp_ctx)
                    _pin_cert_manager_to_control_plane(cp_ctx)
                    _wait_for_cert_manager(cp_ctx)
                    ms.done(h, detail=f"version={CERT_MANAGER_VERSION}")

                    if not args.skip_service_monitor_crd:
                        h = ms.start(f"Install ServiceMonitor CRD on {cp.cluster_name} (operator apiserver watch)")
                        _install_service_monitor_crd(cp_ctx)
                        ms.done(h, detail=f"prometheus-operator {PROMETHEUS_OPERATOR_VERSION}")
                    else:
                        ms.skip(f"Install ServiceMonitor CRD on {cp.cluster_name}", reason="--skip-service-monitor-crd set")

                _helm_upgrade_install(
                    context=cp_ctx,
                    chart_dir=GIT_ROOT_DIR,
                    release_name=settings.release_name,
                    namespace=settings.namespace,
                    values_file=cp_values_files[cp.cluster_name],
                    base_values_files=(
                        _version_specific_values_file(settings.chart_version),
                        GIT_ROOT_DIR / "configs" / "postgres-enabled.yaml",
                    ),
                    extra_values_files=[Path(f) for f in args.helm_values],
                    timeout=settings.helm_timeout,
                    debug=settings.helm_debug,
                    chart_version=settings.chart_version,
                    chart_is_prerelease=settings.chart_is_prerelease,
                    extra_set=settings.extra_helm_set,
                )
                ms.done(h)

            # Step: create astronomer-bootstrap secrets in DP clusters using MySQL.
            # Postgres mode needs no manual step: the `postgresql` subchart's own
            # astronomer-bootstrap-secret.yaml template creates it automatically whenever
            # `global.postgresql.enabled: true` (see charts/postgresql/templates/) — creating it
            # ourselves via kubectl first would make Helm refuse to install (a resource with that
            # name already exists but isn't Helm-owned).
            if settings.dp_airflow_db == "mysql":
                h = ms.start("Create DP astronomer-bootstrap secrets (MySQL)")
                for dp in settings.data_planes:
                    _create_astronomer_bootstrap_secret_mysql(
                        context=f"k3d-{dp.cluster_name}",
                        namespace=settings.namespace,
                        release_name=settings.release_name,
                    )
                ms.done(h, detail=f"db={settings.dp_airflow_db}")
            else:
                ms.skip("Create DP astronomer-bootstrap secrets", reason="postgresql subchart creates it automatically")

            # IMPORTANT: DP components may need to resolve CP endpoints during startup.
            # Patch each DP's CoreDNS NodeHosts (and restart CoreDNS) after CP install, before that DP's install.
            for dp in settings.data_planes:
                dp_ctx = f"k3d-{dp.cluster_name}"
                if not args.skip_dns_reconcile:
                    h = ms.start(f"Pre-DP: update {dp.cluster_name} CoreDNS NodeHosts for CP ingress")
                    _run_dns_reconcile(settings, settings.control_planes[0], dp)
                    ms.done(h)
                else:
                    ms.skip(f"Pre-DP: update {dp.cluster_name} CoreDNS NodeHosts for CP ingress", reason="--skip-dns-reconcile set")

                # The airflow-operator webhooks need cert-manager's Issuer/Certificate
                # flow to produce `webhook-server-cert`. Install cert-manager before the
                # DP helm release so the Certificate the chart creates can be fulfilled.
                if settings.enable_operator:
                    h = ms.start(f"Install cert-manager on {dp.cluster_name} (operator webhooks)")
                    _install_cert_manager(dp_ctx)
                    _pin_cert_manager_to_control_plane(dp_ctx)
                    _wait_for_cert_manager(dp_ctx)
                    ms.done(h, detail=f"version={CERT_MANAGER_VERSION}")

                    if not args.skip_service_monitor_crd:
                        h = ms.start(f"Install ServiceMonitor CRD on {dp.cluster_name} (operator apiserver watch)")
                        _install_service_monitor_crd(dp_ctx)
                        ms.done(h, detail=f"prometheus-operator {PROMETHEUS_OPERATOR_VERSION}")
                    else:
                        ms.skip(f"Install ServiceMonitor CRD on {dp.cluster_name}", reason="--skip-service-monitor-crd set")

                # Each DP runs its own database — postgres subchart on, unless --dp-airflow-db=mysql
                # (mysql is deployed as a plain k8s manifest above instead; see _deploy_mysql).
                dp_postgres_values_file = (
                    "postgres-enabled.yaml" if settings.dp_airflow_db == "postgres" else "postgres-disabled.yaml"
                )

                h = ms.start(f"Helm install/upgrade Data Plane (context={dp_ctx})")
                _helm_upgrade_install(
                    context=dp_ctx,
                    chart_dir=GIT_ROOT_DIR,
                    release_name=settings.release_name,
                    namespace=settings.namespace,
                    values_file=dp_values_files[dp.cluster_name],
                    base_values_files=(
                        _version_specific_values_file(settings.chart_version),
                        GIT_ROOT_DIR / "configs" / dp_postgres_values_file,
                    ),
                    extra_values_files=[Path(f) for f in args.helm_values],
                    timeout=settings.helm_timeout,
                    debug=settings.helm_debug,
                    chart_version=settings.chart_version,
                    chart_is_prerelease=settings.chart_is_prerelease,
                    extra_set=settings.extra_helm_set,
                )
                ms.done(h)
        else:
            ms.skip("Helm dependency update + CP/DP install", reason="--skip-helm set")

        # Step: DNS reconcile (final, once per DP against the primary CP)
        for dp in settings.data_planes:
            if not args.skip_dns_reconcile:
                h = ms.start(f"Reconcile cross-cluster DNS + node-level hosts pins ({dp.cluster_name})")
                _run_dns_reconcile(settings, settings.control_planes[0], dp)
                ms.done(h)
            else:
                ms.skip(
                    f"Reconcile cross-cluster DNS + node-level hosts pins ({dp.cluster_name})", reason="--skip-dns-reconcile set"
                )

        # Step: DP node-level houston.<baseDomain> pin (node-level DNS for kubelet/containerd-like operations)
        for dp in settings.data_planes:
            if not args.skip_node_registry_check:
                h = ms.start(f"DP node: pin houston.<baseDomain> to CP ingress ({dp.cluster_name} /etc/hosts)")
                _ensure_dp_node_houston_hosts_pin(settings, dp)
                ms.done(h)
            else:
                ms.skip(
                    f"DP node: pin houston.<baseDomain> to CP ingress ({dp.cluster_name} /etc/hosts)",
                    reason="--skip-node-registry-check set",
                )

        # Step: local DNS + SNI proxy (replaces manual host /etc/hosts editing)
        if not args.skip_local_networking:
            h = ms.start(f"Configure local DNS + SNI proxy for `{settings.base_domain}` (no /etc/hosts editing)")
            try:
                detail = _setup_local_networking(settings)
                ms.done(h, detail=detail)
            except Exception as e:  # noqa: BLE001
                ms.fail(h, error=str(e))
                _print(f"\n⚠️  Local networking setup failed ({e}); falling back to manual /etc/hosts instructions.")
                _print_manual_etc_hosts_fallback(settings)
        else:
            ms.skip("Configure local DNS + SNI proxy", reason="--skip-local-networking set")
            _print_manual_etc_hosts_fallback(settings)

        ms.print_summary_table()
        _print("\n✅ Completed.")
        return 0
    except Exception as e:  # noqa: BLE001
        ms.fail_active_if_any(error=str(e))
        ms.print_summary_table()
        _print(f"\n❌ Failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
