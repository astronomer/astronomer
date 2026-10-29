"""istio-gateway: platform north-south routing through a real Istio Gateway instead of nginx Ingress.

With global.istio.gateway.enabled, every platform Ingress template short-circuits (the
`if not istio.gateway.enabled` guard at the top of each one) and a VirtualService is
rendered in its place. tests/chart_tests/test_istio_virtualservice.py already covers what
that renders; everything here is deliberately scoped to the things a template-level test
structurally cannot check:

  1. (test_virtualservices_exist) The Istio API server ACCEPTS the chart's objects. The
     chart hardcodes networking.istio.io/v1alpha3 (templates/_apivers.tpl's
     apiVersion.istio.networking helper). A rendered manifest stays valid forever; a served
     API version does not. When Istio eventually stops serving v1alpha3, `helm install`
     starts failing and this is the test that says so.

  2. (test_virtualservice_gateway_references_resolve) Every VirtualService's gateways[]
     entry names a Gateway that really exists. This is the specific silent failure the
     comment on global.istio.gateway in values.yaml warns about: a VirtualService pointing
     at a nonexistent Gateway is accepted by the API server and routes nothing, so the
     install "succeeds" and the platform is unreachable. No amount of `helm template`
     inspection can catch a dangling reference.

  3. (test_gateway_routes_houston and below) Real HTTP through the gateway's Envoy. The
     Houston VirtualService's first rule is a fault-injection abort returning 403 for
     ^/v1/(alerts|metrics).* (charts/astronomer/templates/houston/houston-virtualservice.yaml),
     with everything else falling through to Houston's Service. Asserting the 403 and the
     non-403 proves an Envoy actually evaluated the routing rules, not just that the YAML
     said so. Same for the bare-domain 301 redirect the common VirtualService defines, and
     for reaching grafana through its auth-proxy sidecar.

Istio itself and the Gateway are created pre-helm by bin/setup-istio.py -- see that
script's docstring for why both have to exist before the platform install rather than
after.

Deliberately out of scope:
  - Everything behind global.istio.enabled, which this scenario leaves OFF
    (configs/enable-istio-gateway.yaml). That flag renders the mesh Sidecar objects
    (charts/astronomer/templates/istio/sidecars.yaml), one of which lives in
    global.istio.rootNamespace -- a namespace nothing in this scenario creates. It also
    does not label any namespace for injection, so covering it properly means putting an
    Envoy sidecar in front of every platform component, bringing in mTLS, probe rewriting,
    and the NATS/Elasticsearch ports. That is a much larger scenario than the Gateway
    ingress path, which is what global.istio.gateway.enabled alone controls and what this
    scenario tests.
  - The commander VirtualServices. Both gate on `plane.mode == "data"` exactly
    (commander-grpc-virtualservice.yaml, commander-metadata-virtualservice.yaml), so they
    never render in this scenario's unified topology; covering them needs a data-topology
    scenario of its own.
  - HTTPS at the gateway. bin/setup-istio.py's Gateway serves HTTP only; VirtualServices
    attach to a Gateway by name regardless of protocol, so TLS termination would exercise
    no additional chart code.
"""

import contextlib
import socket
import subprocess
import time

import pytest
import requests
from kubernetes import client, config

from tests.utils.k8s import KUBECONFIG_UNIFIED

# See bin/setup-istio.py and configs/enable-istio-gateway.yaml -- these MUST match both.
PLATFORM_NAMESPACE = "astronomer"
ISTIO_NAMESPACE = "istio-system"
GATEWAY_NAME = "astronomer-gateway"
INGRESS_GATEWAY_SERVICE = "istio-ingressgateway"
INGRESS_GATEWAY_PORT = 80

# configs/local-dev.yaml's global.baseDomain, and the helm release name helm-install.py uses.
BASE_DOMAIN = "localtest.me"
RELEASE_NAME = "astronomer"

ISTIO_GROUP = "networking.istio.io"
# The version the chart itself emits (templates/_apivers.tpl). Queried explicitly rather
# than via a newer served version, so these tests fail if the chart's version is dropped.
ISTIO_VERSION = "v1alpha3"

# Every VirtualService the unified topology renders, and the single host each one claims.
# Taken from the chart's own templates; a drift here is a real change in the platform's
# externally reachable surface, which is worth failing on rather than discovering live.
EXPECTED_VIRTUALSERVICES = {
    f"{RELEASE_NAME}-alertmanager-virtualservice": f"alertmanager.{BASE_DOMAIN}",
    f"{RELEASE_NAME}-astroui-virtualservice": f"app.{BASE_DOMAIN}",
    f"{RELEASE_NAME}-common-virtualservice": BASE_DOMAIN,
    f"{RELEASE_NAME}-elasticsearch-virtualservice": f"elasticsearch.{BASE_DOMAIN}",
    f"{RELEASE_NAME}-grafana-virtualservice": f"grafana.{BASE_DOMAIN}",
    f"{RELEASE_NAME}-houston-virtualservice": f"houston.{BASE_DOMAIN}",
    f"{RELEASE_NAME}-prometheus-virtualservice": f"prometheus.{BASE_DOMAIN}",
    f"{RELEASE_NAME}-registry-virtualservice": f"registry.{BASE_DOMAIN}",
}

# Houston's health endpoint (see the commented-out livenessProbe example in
# charts/astronomer/values.yaml). Does NOT match the fault-injection regex, so it must fall
# through to Houston's Service -- the positive half of the fault-injection assertion.
HOUSTON_HEALTH_PATH = "/v1/healthz"
# The paths houston-virtualservice.yaml's ^/v1/(alerts|metrics).* rule aborts with a 403.
HOUSTON_BLOCKED_PATHS = ("/v1/alerts", "/v1/metrics")

# global.authSidecar.port. With the auth sidecar enabled these three admin UIs'
# VirtualServices route here instead of to the component's own port, so this is where
# gateway routing and the auth proxy meet.
AUTH_SIDECAR_PORT = 8084
AUTH_SIDECAR_VIRTUALSERVICES = (
    f"{RELEASE_NAME}-alertmanager-virtualservice",
    f"{RELEASE_NAME}-grafana-virtualservice",
    f"{RELEASE_NAME}-prometheus-virtualservice",
)


@pytest.fixture(scope="module")
def _custom_objects_client() -> client.CustomObjectsApi:
    """Module-scoped (conftest's clients are function-scoped and can't back a module-scoped fixture)."""
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CustomObjectsApi()


@pytest.fixture(scope="module")
def _networking_v1_client() -> client.NetworkingV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.NetworkingV1Api()


def _list_istio_objects(custom_objects_client: client.CustomObjectsApi, plural: str, namespace: str) -> dict:
    """{name: object} for one Istio kind in one namespace, via the chart's own API version."""
    response = custom_objects_client.list_namespaced_custom_object(
        group=ISTIO_GROUP, version=ISTIO_VERSION, namespace=namespace, plural=plural
    )
    return {item["metadata"]["name"]: item for item in response["items"]}


@contextlib.contextmanager
def _port_forward(service: str, namespace: str, remote_port: int):
    """Port-forward a Service to a free local port; yields that local port.

    kind has no LoadBalancer provisioner and *.localtest.me resolves to 127.0.0.1 without
    reaching the cluster, so the gateway is driven over a port-forward with an explicit
    Host header rather than through DNS -- which is also what makes the host-based routing
    assertions below unambiguous: every request takes the identical network path and
    differs only in the Host header Envoy routes on.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        local_port = s.getsockname()[1]
    proc = subprocess.Popen(
        [
            "kubectl",
            f"--kubeconfig={KUBECONFIG_UNIFIED}",
            "port-forward",
            f"svc/{service}",
            f"{local_port}:{remote_port}",
            "-n",
            namespace,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", local_port), timeout=1):
                break
            time.sleep(0.5)
        yield local_port
    finally:
        proc.terminate()
        proc.wait()


@pytest.fixture(scope="module")
def gateway_port():
    """One port-forward to the ingress gateway for the whole module."""
    with _port_forward(INGRESS_GATEWAY_SERVICE, ISTIO_NAMESPACE, INGRESS_GATEWAY_PORT) as local_port:
        yield local_port


def _get_through_gateway(gateway_port: int, host: str, path: str = "/", allow_redirects: bool = False):
    """GET path through the ingress gateway, routed by the Host header alone."""
    return requests.get(
        f"http://127.0.0.1:{gateway_port}{path}",
        headers={"Host": host},
        allow_redirects=allow_redirects,
        timeout=30,
    )


def test_virtualservices_exist(_custom_objects_client):
    """The Istio API server accepted every VirtualService the chart renders, at the chart's
    own apiVersion. An empty or short list here most likely means v1alpha3 is no longer
    served, or the install silently skipped these objects."""
    found = _list_istio_objects(_custom_objects_client, "virtualservices", PLATFORM_NAMESPACE)

    missing = set(EXPECTED_VIRTUALSERVICES) - set(found)
    assert not missing, (
        f"These VirtualServices are not in {PLATFORM_NAMESPACE} at {ISTIO_GROUP}/{ISTIO_VERSION}: "
        f"{sorted(missing)} (found {sorted(found)}). If none exist at all, check whether this "
        f"Istio version still serves {ISTIO_VERSION} -- the chart hardcodes it."
    )


def test_virtualservice_hosts(_custom_objects_client):
    """Each VirtualService claims the host the platform publishes it on."""
    found = _list_istio_objects(_custom_objects_client, "virtualservices", PLATFORM_NAMESPACE)

    wrong = {}
    for name, expected_host in EXPECTED_VIRTUALSERVICES.items():
        hosts = found[name]["spec"]["hosts"]
        if hosts != [expected_host]:
            wrong[name] = {"expected": [expected_host], "actual": hosts}
    assert not wrong, f"VirtualService hosts do not match the platform's published hostnames: {wrong}"


def test_no_sidecar_objects(_custom_objects_client):
    """global.istio.enabled is off, so the chart's mesh Sidecar objects must not exist.

    The fail-closed counterpart to this scenario's scope: gateway.enabled and istio.enabled
    are independent flags, and only the former is on here. If a Sidecar shows up, a template
    has started rendering on the wrong flag -- which would also mean the install depends on
    global.istio.rootNamespace existing, and nothing in this scenario creates it.
    """
    found = _list_istio_objects(_custom_objects_client, "sidecars", PLATFORM_NAMESPACE)

    assert not found, (
        f"global.istio.enabled is false, so no Sidecar objects should exist, but "
        f"{PLATFORM_NAMESPACE} has: {sorted(found)}. Check whether "
        f"charts/astronomer/templates/istio/sidecars.yaml is still gated on global.istio.enabled."
    )


def test_no_platform_ingresses(_networking_v1_client):
    """Enabling the Gateway suppresses every platform Ingress, live. The ingress templates
    and the VirtualService templates are gated on the same flag in opposite directions, so a
    guard dropped from one ingress template leaves both objects serving the same host."""
    ingresses = _networking_v1_client.list_namespaced_ingress(PLATFORM_NAMESPACE).items

    names = [ingress.metadata.name for ingress in ingresses]
    assert not names, (
        f"global.istio.gateway.enabled is on, so no platform Ingress should exist, but "
        f"{PLATFORM_NAMESPACE} has: {sorted(names)}. Each ingress template must short-circuit "
        f"on `if not istio.gateway.enabled`."
    )


def test_virtualservice_gateway_references_resolve(_custom_objects_client):
    """Every gateways[] entry names a Gateway that exists.

    A dangling reference is accepted by the API server and silently routes nothing, which is
    exactly why global.istio.gateway.name has no default (see values.yaml). This resolves
    each reference against the cluster instead of trusting the rendered string.
    """
    found = _list_istio_objects(_custom_objects_client, "virtualservices", PLATFORM_NAMESPACE)

    dangling = {}
    for name in EXPECTED_VIRTUALSERVICES:
        for reference in found[name]["spec"]["gateways"]:
            namespace, _, gateway_name = reference.partition("/")
            assert gateway_name, (
                f"VirtualService {name} references gateway {reference!r}, which is not in "
                f"<namespace>/<name> form, so it resolves relative to the VirtualService's own "
                f"namespace rather than where the Gateway was created."
            )
            try:
                _custom_objects_client.get_namespaced_custom_object(
                    group=ISTIO_GROUP, version=ISTIO_VERSION, namespace=namespace, plural="gateways", name=gateway_name
                )
            except client.exceptions.ApiException as exc:
                if exc.status != 404:
                    raise
                dangling[name] = reference

    assert not dangling, (
        f"These VirtualServices attach to a Gateway that does not exist, so they are accepted "
        f"by the API server and route nothing: {dangling}"
    )


@pytest.mark.flaky(reruns=10, reruns_delay=6)
def test_gateway_routes_houston(gateway_port):
    """The headline assertion: a real request through the gateway's Envoy reaches Houston.

    Flaky-marked for istiod's xDS push, not for anything about Houston: the Gateway and
    VirtualServices exist well before this runs, but Envoy only serves a route once istiod
    has pushed the config to it.
    """
    response = _get_through_gateway(gateway_port, f"houston.{BASE_DOMAIN}", HOUSTON_HEALTH_PATH)

    assert response.status_code == 200, (
        f"GET {HOUSTON_HEALTH_PATH} through the gateway as houston.{BASE_DOMAIN} returned "
        f"{response.status_code}, not 200. A 404 means Envoy has no route for this host (the "
        f"VirtualService is not attached to the Gateway this gateway pod serves); a 503 means "
        f"the route exists but Houston's Service has no ready endpoints. Body: {response.text[:500]}"
    )


@pytest.mark.flaky(reruns=10, reruns_delay=6)
@pytest.mark.parametrize("path", HOUSTON_BLOCKED_PATHS)
def test_houston_alerts_and_metrics_are_blocked(gateway_port, path):
    """The Houston VirtualService's fault-injection rule returns 403 for
    ^/v1/(alerts|metrics).* before anything reaches Houston.

    Only a real Envoy produces this: the rule is a routing-layer abort, not something Houston
    itself implements, so a chart test asserting the rendered YAML cannot tell whether the
    regex actually matches the paths it is meant to block. Paired with
    test_gateway_routes_houston, which proves a non-matching path is NOT blocked -- together
    they pin the regex's boundary rather than just its presence.
    """
    response = _get_through_gateway(gateway_port, f"houston.{BASE_DOMAIN}", path)

    assert response.status_code == 403, (
        f"GET {path} through the gateway as houston.{BASE_DOMAIN} returned {response.status_code}, "
        f"not the 403 the VirtualService's fault-injection abort should produce. A 200 means the "
        f"^/v1/(alerts|metrics).* rule did not match and the request reached Houston."
    )


@pytest.mark.flaky(reruns=10, reruns_delay=6)
def test_bare_domain_redirects_to_app_subdomain(gateway_port):
    """The common VirtualService 301-redirects the bare base domain to app.<baseDomain>."""
    response = _get_through_gateway(gateway_port, BASE_DOMAIN)

    assert response.status_code == 301, (
        f"GET / through the gateway as {BASE_DOMAIN} returned {response.status_code}, not the 301 "
        f"the common VirtualService's redirect should produce."
    )
    assert response.headers.get("location") == f"https://app.{BASE_DOMAIN}/", (
        f"Bare-domain redirect pointed at {response.headers.get('location')!r} instead of https://app.{BASE_DOMAIN}/"
    )


@pytest.mark.parametrize("virtualservice", AUTH_SIDECAR_VIRTUALSERVICES)
def test_admin_ui_virtualservices_route_to_the_auth_sidecar(_custom_objects_client, virtualservice):
    """With global.authSidecar enabled, the admin UIs' VirtualServices route to the auth
    proxy's port rather than the component's own.

    Read off the live object rather than a rendered one: nginx is disabled in this scenario,
    so the auth proxy is the only thing in front of these components, and a VirtualService
    still pointing at grafana:3000 would bypass authentication entirely while looking healthy.
    """
    found = _list_istio_objects(_custom_objects_client, "virtualservices", PLATFORM_NAMESPACE)

    ports = {
        route["destination"]["port"]["number"] for http in found[virtualservice]["spec"]["http"] for route in http.get("route", [])
    }
    assert ports == {AUTH_SIDECAR_PORT}, (
        f"{virtualservice} routes to port(s) {sorted(ports)}, not the auth sidecar's "
        f"{AUTH_SIDECAR_PORT}. With global.authSidecar enabled and nginx disabled, routing "
        f"straight to the component's own port means unauthenticated access to it."
    )


@pytest.mark.flaky(reruns=10, reruns_delay=6)
def test_gateway_reaches_grafana_through_the_auth_sidecar(gateway_port):
    """A real request through the Gateway reaches grafana's auth proxy.

    Deliberately does not assert an exact status: an unauthenticated request can legitimately
    be answered with a 200 login page, a 302 to an identity provider, or a 401, and which one
    is the auth sidecar's business rather than this scenario's. What it pins instead are the
    ways this wiring actually breaks, each of which has its own status:

      - 404: Envoy has no route for the host (VirtualService not attached to this Gateway).
      - 503: the route exists but the connection is refused -- nothing is serving
        AUTH_SIDECAR_PORT, i.e. the VirtualService names a port the sidecar is not on.
      - 504: the connection is DROPPED rather than refused, which on this chart means
        NetworkPolicy. The admin UIs only admit port 8084 from namespaces in
        global.authSidecar.ingressAllowedNamespaces (plus the OpenShift ingress policy-group
        label), so an istio-system missing from that list times out here while every
        VirtualService still looks perfectly correct.
    """
    response = _get_through_gateway(gateway_port, f"grafana.{BASE_DOMAIN}")

    assert response.status_code != 404, (
        f"GET / through the gateway as grafana.{BASE_DOMAIN} returned 404 -- Envoy has no route "
        f"for this host, so grafana's VirtualService is not attached to the Gateway this gateway "
        f"pod serves."
    )
    assert response.status_code < 500, (
        f"GET / through the gateway as grafana.{BASE_DOMAIN} returned {response.status_code}. The "
        f"route exists but the gateway could not reach the auth sidecar on port "
        f"{AUTH_SIDECAR_PORT}: 503 means refused (wrong port), 504 means dropped -- check that "
        f"global.authSidecar.ingressAllowedNamespaces includes the gateway's namespace, or "
        f"NetworkPolicy is discarding the gateway's traffic."
    )


@pytest.mark.flaky(reruns=10, reruns_delay=6)
def test_unclaimed_host_is_not_routed(gateway_port):
    """A host no VirtualService claims gets no route.

    Fails closed: without this, a gateway misconfigured to serve everything (or a
    VirtualService with hosts: ["*"]) would make every positive assertion above pass for the
    wrong reason.
    """
    response = _get_through_gateway(gateway_port, f"not-a-platform-service.{BASE_DOMAIN}")

    assert response.status_code == 404, (
        f"GET / through the gateway as an unclaimed host returned {response.status_code}, not 404 -- "
        f"the gateway is routing hosts no VirtualService claims."
    )
