#!/usr/bin/env python3
"""Install cert-manager into a test cluster, for scenarios that enable the airflow-operator.

charts/airflow-operator defaults certManager.enabled=true, which renders an Issuer and a
Certificate for the operator's admission webhook. A kind cluster from bin/setup-kind.py has no
cert-manager, so `helm install` fails applying them:

    no matches for kind "Certificate" in version "cert-manager.io/v1"
    no matches for kind "Issuer" in version "cert-manager.io/v1"

Turning it off instead is not an option: charts/airflow-operator/templates/validate-webhook-tls.yaml
refuses to render with both certManager.enabled and webhooks.useCustomTlsCerts false, and the
custom-certs branch needs a pre-created Secret plus a caBundle -- more pre-helm setup, not less.

Run this BEFORE `helm install`, unlike bin/install-kyverno-scan.py which runs after it: Kyverno
only has to exist before the pods it evaluates are created, while these are types the chart's own
manifests refer to. A scenario gets that ordering from `pre_helm_scripts` in its test_profile.yaml.

Also applies the Prometheus Operator ServiceMonitor CRD, and only the CRD -- not Prometheus
Operator itself. The airflow-operator's apiserver controller watches monitoring.coreos.com/v1
ServiceMonitor and its cache never syncs when the type is absent, leaving the manager pod unready.
Pass --skip-service-monitor-crd if the cluster already has it. Both installs are idempotent, and
both mirror what bin/setup-cp-dp-k3d-new.py does for the local k3d topology under --enable-operator.
"""

import argparse
import os
import subprocess
import sys

from k3d_setup_shared import CERT_MANAGER_MANIFEST_URL, CERT_MANAGER_VERSION

PROMETHEUS_OPERATOR_VERSION = "v0.76.0"
SERVICE_MONITOR_CRD_URL = (
    f"https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/{PROMETHEUS_OPERATOR_VERSION}"
    "/example/prometheus-operator-crd/monitoring.coreos.com_servicemonitors.yaml"
)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--kubeconfig",
        default=os.environ.get("KUBECONFIG"),
        help="Path to the kubeconfig for the cluster to install into. Defaults to $KUBECONFIG, which "
        "bin/reset-local-dev already points at the scenario's cluster for every pre_helm_scripts entry.",
    )
    parser.add_argument(
        "--timeout",
        default="300s",
        help="How long to wait for cert-manager's Deployments to become Available (default: %(default)s); "
        "the chart's Issuer is rejected until cert-manager's webhook is serving.",
    )
    parser.add_argument(
        "--skip-service-monitor-crd",
        action="store_true",
        help="Skip the ServiceMonitor CRD. Pass this only if a full Prometheus Operator (or the CRD) "
        "is already installed in the cluster.",
    )
    return parser.parse_args()


def kubectl(kubeconfig: str | None, *args: str) -> None:
    """Run kubectl against `kubeconfig`, echoing the command so a CI log shows what ran."""
    command = ["kubectl", *([f"--kubeconfig={kubeconfig}"] if kubeconfig else []), *args]
    print(f"+ {' '.join(command)}", flush=True)
    subprocess.run(command, check=True)


def install_cert_manager(kubeconfig: str | None, timeout: str) -> None:
    """Apply the cert-manager manifest and wait for its controllers to be Available."""
    print(f"Installing cert-manager {CERT_MANAGER_VERSION}")
    kubectl(kubeconfig, "apply", "-f", CERT_MANAGER_MANIFEST_URL)
    kubectl(kubeconfig, "wait", "--for=condition=Available", f"--timeout={timeout}", "-n", "cert-manager", "deployment", "--all")


def install_service_monitor_crd(kubeconfig: str | None) -> None:
    """Server-side apply just the ServiceMonitor CRD, so the operator's apiserver watch can sync."""
    print(f"Applying the ServiceMonitor CRD from prometheus-operator {PROMETHEUS_OPERATOR_VERSION}")
    kubectl(kubeconfig, "apply", "--server-side", "-f", SERVICE_MONITOR_CRD_URL)


def main() -> None:
    args = parse_args()
    install_cert_manager(args.kubeconfig, args.timeout)
    if not args.skip_service_monitor_crd:
        install_service_monitor_crd(args.kubeconfig)
    print("cert-manager ready; the airflow-operator's webhook Issuer/Certificate can now be applied.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: cert-manager install failed: {e}", file=sys.stderr)
        raise SystemExit(1) from e
