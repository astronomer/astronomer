#!/usr/bin/env python3
"""Pre-helm setup for the istio-gateway scenario.

Installs Istio into the scenario's fresh cluster and creates the Gateway that the
platform's VirtualServices attach to.

Runs via test_profile.yaml's `pre_helm_scripts` -- i.e. after the cluster exists but
BEFORE `helm install` (see tests/functional/scenarios/README.md). It must run pre-helm for
two separate reasons, either of which would fail the platform install on its own:

  - The VirtualService CRD must exist before helm applies the objects the chart renders
    for it. Without istio/base installed first, `helm install` fails outright with
    `no matches for kind "VirtualService"`.
  - global.istio.gateway.name has to name a Gateway that really exists. A VirtualService
    naming a nonexistent Gateway is accepted by the API server and silently routes nothing
    (see the comment on global.istio.gateway in values.yaml), so creating the Gateway
    after install would leave helm reporting success and the platform unreachable -- the
    exact failure this scenario exists to catch.

Does NOT create global.istio.rootNamespace. --root-namespace only sets istiod's own
meshConfig.rootNamespace. The chart puts a mesh-default Sidecar in that namespace, but only
when global.istio.enabled is true, which the istio-gateway scenario leaves off (it tests
the Gateway ingress path, not sidecar injection). Turning global.istio.enabled on means
creating that namespace here first, or `helm install` fails applying the Sidecar into a
namespace that does not exist.

Installs the three official Istio charts straight from their release tarball URLs rather
than via `helm repo add`, so a developer's own helm repository list is left untouched.

The Gateway serves plain HTTP on :80 for all hosts. The platform's VirtualServices attach
to a Gateway by name regardless of its protocol, so terminating TLS here would add a cert
to manage in istio-system without exercising any additional chart code path.

This creates a namespace and installs helm releases in whatever cluster KUBECONFIG points
at. The namespaces and Gateway name are REQUIRED and have no defaults, precisely so an
accidental invocation (e.g. running it to read `--help`) cannot mutate your current
context: with no arguments it aborts before touching the cluster. They must match
configs/enable-istio-gateway.yaml's global.istio values. reset-local-dev exports KUBECONFIG
at the fresh scenario cluster and puts helm and kubectl on PATH.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

GIT_ROOT_DIR = next((p for p in Path(__file__).resolve().parents if (p / ".git").exists()), None)
if GIT_ROOT_DIR is None:
    raise SystemExit(f"ERROR: could not locate the repository root: no .git entry found above {Path(__file__).resolve()}")
CHART_METADATA = yaml.safe_load((GIT_ROOT_DIR / "metadata.yaml").read_text())
ISTIO_VERSION = CHART_METADATA["tools"]["istio"]["version"]
CHART_BASE_URL = "https://istio-release.storage.googleapis.com/charts"

# The label the istio/gateway chart puts on its pods when the release is named
# "istio-ingressgateway" (it strips the leading "istio-"), and therefore the selector the
# Gateway below must use to bind to that Envoy. Asserted rather than assumed -- see
# verify_gateway_workload().
GATEWAY_RELEASE_NAME = "istio-ingressgateway"
GATEWAY_SELECTOR_LABEL = "istio=ingressgateway"

# CRDs needed before anything else is applied: virtualservices for the astronomer chart's
# own objects, gateways for the Gateway created below. sidecars is included because the
# chart renders Sidecar objects as soon as global.istio.enabled is turned on, and the cost
# of waiting for a CRD that is already there is nil. Waited on explicitly so a CRD that has
# not finished establishing surfaces here, rather than as a confusing `helm install` failure.
REQUIRED_CRDS = (
    "gateways.networking.istio.io",
    "sidecars.networking.istio.io",
    "virtualservices.networking.istio.io",
)

# istiod's defaults request 500m/2Gi, which is a meaningful share of a CI node that also
# has to fit the whole platform chart (see configs/scenario-airflow-reduce-resources.yaml
# and PINF-1080 for the same concern). This scenario only routes a handful of requests
# through one gateway, so it does not need a production-sized control plane.
ISTIOD_SETTINGS = (
    "pilot.resources.requests.cpu=100m",
    "pilot.resources.requests.memory=512Mi",
    "pilot.autoscaleEnabled=false",
)
GATEWAY_SETTINGS = (
    # kind has no LoadBalancer provisioner, so a type=LoadBalancer Service would sit at
    # <pending> forever. The tests reach this Service by port-forward, which needs no
    # external address at all.
    "service.type=ClusterIP",
    "autoscaling.enabled=false",
)


def parse_args() -> argparse.Namespace:
    """Parse (and require) the namespaces and Gateway name. argparse gives `--help` and,
    because nothing has a default, aborts a bare/accidental invocation before any cluster
    mutation."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--root-namespace",
        required=True,
        help="Istio mesh root namespace, set as istiod's meshConfig.rootNamespace (e.g. istio-config). "
        "NOT created -- create it yourself before running this if global.istio.enabled is true, since "
        "the chart puts a Sidecar there. Must equal global.istio.rootNamespace.",
    )
    parser.add_argument(
        "--gateway-namespace",
        required=True,
        help="Namespace Istio itself and the ingress gateway are installed into, created if absent "
        "(e.g. istio-system). Must be the namespace half of global.istio.gateway.name.",
    )
    parser.add_argument(
        "--gateway-name",
        required=True,
        help="Name of the Gateway to create (e.g. astronomer-gateway). Must be the name half of global.istio.gateway.name.",
    )
    return parser.parse_args()


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, echoing it, and fail loudly on non-zero exit."""
    print(f"+ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def kubectl(*args: str) -> subprocess.CompletedProcess:
    """kubectl wrapper (KUBECONFIG comes from the environment set by reset-local-dev)."""
    return run(["kubectl", *args])


def create_namespace(namespace: str) -> None:
    """Create a namespace idempotently. `kubectl create namespace` is not idempotent, so
    render it and apply, which is, for local re-runs against a reused cluster."""
    manifest = subprocess.run(
        ["kubectl", "create", "namespace", namespace, "--dry-run=client", "-o=yaml"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    run(["kubectl", "apply", "-f", "-"], input=manifest, text=True)


def helm_install(release: str, chart: str, namespace: str, settings: tuple[str, ...] = ()) -> None:
    """Install (or upgrade, for local re-runs) one Istio chart from its release tarball URL."""
    cmd = [
        "helm",
        "upgrade",
        "--install",
        release,
        f"{CHART_BASE_URL}/{chart}-{ISTIO_VERSION}.tgz",
        f"--namespace={namespace}",
        "--wait",
        "--timeout=10m0s",
    ]
    cmd.extend(f"--set={setting}" for setting in settings)
    run(cmd)


def wait_for_crds() -> None:
    """Block until the CRDs the astronomer chart's objects need are established."""
    for crd in REQUIRED_CRDS:
        kubectl("wait", "--for=condition=established", f"crd/{crd}", "--timeout=120s")


def verify_gateway_workload(gateway_namespace: str) -> None:
    """Fail if no pod carries the label the Gateway's selector targets.

    A Gateway whose selector matches no workload is accepted by the API server and routes
    nothing -- the same silent-failure shape as naming a nonexistent Gateway. Catching it
    here means a future istio/gateway chart that changes its pod labels fails in this
    script with a clear message, instead of as unexplained connection refusals in the
    scenario's own HTTP assertions.
    """
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", gateway_namespace, "-l", GATEWAY_SELECTOR_LABEL, "-o=name"],
        check=True,
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        raise SystemExit(
            f"ERROR: no pods in {gateway_namespace} carry '{GATEWAY_SELECTOR_LABEL}', so the Gateway's "
            f"selector would match no workload and route nothing. Did the istio/gateway chart "
            f"({ISTIO_VERSION}) change the labels it applies to its pods?"
        )
    print(f"Gateway workload found: {result.stdout.strip()}")


def create_gateway(gateway_namespace: str, gateway_name: str) -> None:
    """Create the Gateway the platform's VirtualServices name.

    Deliberately uses networking.istio.io/v1alpha3 -- the same API version the chart's own
    objects use (see the apiVersion.istio.networking helper in templates/_apivers.tpl) --
    so this scenario exercises the version the platform actually ships rather than a newer
    one Istio happens to also serve.
    """
    manifest = f"""
apiVersion: networking.istio.io/v1alpha3
kind: Gateway
metadata:
  name: {gateway_name}
  namespace: {gateway_namespace}
spec:
  selector:
    {GATEWAY_SELECTOR_LABEL.replace("=", ": ")}
  servers:
    - port:
        number: 80
        name: http
        protocol: HTTP
      hosts:
        - "*"
"""
    run(["kubectl", "apply", "-f", "-"], input=manifest, text=True)


def main() -> None:
    args = parse_args()
    print(f"Installing Istio {ISTIO_VERSION} into {args.gateway_namespace} (mesh root namespace: {args.root_namespace})")

    create_namespace(args.gateway_namespace)
    # The mesh root namespace is deliberately NOT created: nothing puts an object there
    # unless global.istio.enabled is on, and istiod is happy with a rootNamespace that does
    # not exist (it watches it and finds nothing). See this script's docstring.

    # CRDs first: istiod's own objects, and everything the astronomer chart renders, need them.
    helm_install("istio-base", "base", args.gateway_namespace)
    wait_for_crds()

    helm_install(
        "istiod",
        "istiod",
        args.gateway_namespace,
        (f"meshConfig.rootNamespace={args.root_namespace}", *ISTIOD_SETTINGS),
    )
    helm_install(GATEWAY_RELEASE_NAME, "gateway", args.gateway_namespace, GATEWAY_SETTINGS)

    verify_gateway_workload(args.gateway_namespace)
    create_gateway(args.gateway_namespace, args.gateway_name)
    # Read it back: a Gateway rejected by istiod's validating webhook would otherwise only
    # show up later as every VirtualService attaching to nothing.
    kubectl("get", "gateway", args.gateway_name, "-n", args.gateway_namespace)
    print(f"Istio ready: Gateway {args.gateway_namespace}/{args.gateway_name} is in place for the platform install")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: istio setup failed: {e}", file=sys.stderr)
        raise SystemExit(1) from e
