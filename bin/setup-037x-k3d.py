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
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from k3d_setup_shared import (
    CERT_MANAGER_VERSION,
    HELM_CHART,
    HELM_REPO_NAME,
    Milestones,
    _debug,
    _delete_k3d_cluster,
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

DEFAULT_CHART_VERSION = "0.37.7"


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

    base = settings.base_domain
    sans = [base, f"*.{base}"]
    _generate_tls_cert(mkcert_exe=mkcert_exe, cert_path=cert_path, key_path=key_path, root_ca=root_ca, sans=sans)

    return cert_path, key_path, root_ca


def _values_yaml(settings: Settings) -> str:
    """Generate 0.37.x-schema values for a local single-cluster deployment."""
    return f"""\
global:
  airflowOperator:
    enabled: true
  baseDomain: {settings.base_domain}
  tlsSecret: {settings.tls_secret_name}
  postgresqlEnabled: true
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
  postgresql: true
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
        memory: "512Mi"
      limits:
        cpu: "500m"
        memory: "1536Mi"
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

airflow-operator:
  crd:
    create: true
  certManager:
    enabled: true
"""


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
        "--num-compute-nodes",
        dest="num_compute_nodes",
        type=int,
        default=0,
        help="Number of additional k3d worker nodes to create alongside the server node (mapped to k3d --agents). Default: %(default)s. Prefer allocating more CPU/memory in Docker Desktop over adding nodes.",
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
        agents=args.num_compute_nodes,
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
            h = ms.start(f"Install cert-manager {CERT_MANAGER_VERSION} (required by airflow-operator webhooks)")
            _install_cert_manager(context)
            _pin_cert_manager_to_control_plane(context)
            _wait_for_cert_manager(context)
            ms.done(h)

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
