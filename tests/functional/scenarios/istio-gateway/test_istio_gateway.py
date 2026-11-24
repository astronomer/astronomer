"""istio-gateway: platform north-south routing through a real Istio Gateway instead of nginx Ingress.

With global.istio.gateway.enabled, every platform Ingress template short-circuits (the
`if not istio.gateway.enabled` guard at the top of each one) and a VirtualService is
rendered in its place. tests/chart_tests/test_istio_virtualservice.py already covers what
that renders; everything here is deliberately scoped to the things a template-level test
structurally cannot check:

  1. (test_virtualservices_exist) The Istio API server ACCEPTS the chart's objects. The
     chart hardcodes networking.istio.io/v1 (templates/_apivers.tpl's
     apiVersion.istio.networking helper). A rendered manifest stays valid forever; a served
     API version does not. When Istio eventually stops serving that version, `helm install`
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
     for test_gateway_reaches_the_auth_sidecar, which asserts the admin UIs answer from
     their auth proxy rather than from Envoy -- what notices
     global.authSidecar.ingressAllowedNamespaces losing the gateway's namespace at the
     auth-proxy tier (houston's own NetworkPolicy reads that value too, so
     test_gateway_routes_houston fails on the same misconfiguration).

  4. (test_auth_sidecar_runs_on_the_port_the_gateway_routes_to) The auth sidecar the Gateway
     requires is actually running. templates/validate-istio-gateway-auth-sidecar.yaml makes
     global.authSidecar.enabled a precondition of global.istio.gateway.enabled, and
     tests/chart_tests/test_istio_virtualservice.py covers that render-time abort -- but the
     guard only reads two values and never looks at a pod, so only a live install can show
     the proxy it forced on is serving the port the VirtualServices route to.

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
  - A *successfully authenticated* request through an admin UI's auth proxy. The proxy's own
    auth subrequest is `proxy_pass https://houston.<baseDomain>/v1/authorization`
    (charts/grafana/templates/grafana-auth-sidecar-configmap.yaml), i.e. a PUBLIC hostname.
    `localtest.me` resolves to 127.0.0.1 and CoreDNS has no rewrite for it, so inside the
    pod that subrequest reaches its own loopback:443, where nothing listens -- nginx answers
    the subrequest 502 and the client 500. Not an Istio problem and not a chart bug: pod DNS
    resolves the public hostname to loopback with nginx ingress just the same, which is why
    the auth-sidecar scenario only asserts the container's presence and never drives a
    request through it. Getting a 200/302/401 out of the proxy would need a CoreDNS rewrite
    pointing the base domain at the gateway AND TLS on the gateway (see above). The 500 is
    still a response the proxy produced, though, which is what
    test_gateway_reaches_the_auth_sidecar asserts on -- so the routing, the port and the
    NetworkPolicy are all covered without it.
"""

import contextlib
import socket
import subprocess
import time

import pytest
import requests
import testinfra
import yaml
from kubernetes import client, config

from tests import git_root_dir
from tests.utils.houston_graphql import (
    HoustonError,
    create_user,
    create_workspace,
    dump_pod_logs,
    get_cluster_id,
    upsert_deployment,
    wait_for_release_ready,
)
from tests.utils.k8s import KUBECONFIG_UNIFIED, get_pod_by_label_selector

PLATFORM_NAMESPACE = "astronomer"
# Read out of the overlay rather than restated, so the Gateway these tests resolve references
# against is by construction the one the install was pointed at. global.istio.gateway.name is
# the <namespace>/<name> of a Gateway that must already exist, which makes it the single value
# that fixes both. The third copy -- test_profile.yaml's pre_helm_scripts arguments -- cannot be
# derived this way: bin/setup-istio.py runs before helm and creates the Gateway, so it has no
# values to read and deliberately requires the namespace and name as explicit arguments (see
# its docstring). A mismatch between that invocation and this file now surfaces as
# test_virtualservice_gateway_references_resolve failing on a Gateway that does not exist,
# rather than as two constants that silently agree with each other and not with the cluster.
ISTIO_GATEWAY_OVERLAY = git_root_dir / "configs" / "enable-istio-gateway.yaml"
ISTIO_NAMESPACE, _, GATEWAY_NAME = yaml.safe_load(ISTIO_GATEWAY_OVERLAY.read_text())["global"]["istio"]["gateway"][
    "name"
].partition("/")
assert ISTIO_NAMESPACE and GATEWAY_NAME, (
    f"{ISTIO_GATEWAY_OVERLAY}'s global.istio.gateway.name must be in <namespace>/<name> form, so these "
    f"tests know which namespace to resolve the Gateway and port-forward the ingress gateway in."
)
INGRESS_GATEWAY_SERVICE = "istio-ingressgateway"
INGRESS_GATEWAY_PORT = 80

# configs/local-dev.yaml's global.baseDomain, and the helm release name helm-install.py uses.
BASE_DOMAIN = "localtest.me"
RELEASE_NAME = "astronomer"

ISTIO_GROUP = "networking.istio.io"
# The version the chart itself emits (templates/_apivers.tpl's apiVersion.istio.networking).
# Queried explicitly rather than via whatever else the cluster happens to serve, so these
# tests fail if the chart's version is dropped. tests/chart_tests/test_istio_api_version.py
# holds the chart side of this; the two must move together.
ISTIO_VERSION = "v1"

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
# The sidecar container's name, identical in all three charts -- see the `- name: auth-proxy`
# entry in charts/grafana/templates/grafana-deployment.yaml and its prometheus/alertmanager
# statefulset counterparts.
AUTH_SIDECAR_CONTAINER = "auth-proxy"
# The components whose VirtualServices are redirected to the auth proxy. Each `component`
# label selects exactly one single-replica workload in the platform namespace, so one
# constant drives both the VirtualService names below and the pods the sidecar must run in.
AUTH_SIDECAR_COMPONENTS = ("alertmanager", "grafana", "prometheus")
AUTH_SIDECAR_VIRTUALSERVICES = tuple(f"{RELEASE_NAME}-{component}-virtualservice" for component in AUTH_SIDECAR_COMPONENTS)

# The statuses Envoy itself returns when it never got a response from the auth proxy at all,
# as opposed to a response the proxy produced. Measured against this scenario's own cluster
# (calico enforcing, istio-system removed from global.authSidecar.ingressAllowedNamespaces):
#   - 404: Envoy has no route for the host -- the VirtualService is not attached to this Gateway.
#   - 503: what the NetworkPolicy case actually produces. Calico DROPS the gateway's packets, so
#     Envoy sits in connect-timeout for ~30s and answers 503 with `upstream connect error ...
#     reset reason: connection timeout` and no x-envoy-upstream-service-time header. The same
#     status also covers an outright refusal, i.e. nothing serving AUTH_SIDECAR_PORT.
#   - 504: not observed for either failure above, kept because a response-timeout (rather than a
#     connect-timeout) is the same class of "the proxy never answered".
# A reached proxy returns 500 here in ~0.02s; see test_gateway_reaches_the_auth_sidecar.
GATEWAY_UNREACHED_STATUSES = (404, 503, 504)
# Must outlast Envoy's ~30s connect-timeout on the blocked path, or requests raises ReadTimeout
# before the 503 arrives and the failure reports as a client timeout rather than as the routing
# failure it is. Only ever costs time when something is actually broken.
GATEWAY_UNREACHED_TIMEOUT = 60

# The Airflow Deployment this scenario creates, to cover the commander-metadata -> airflow-chart
# VirtualService path. Houston rejects a password that fails its complexity rules or repeats the
# email's local part, so this reuses the pair every other deployment-creating scenario uses.
ADMIN_EMAIL = "istio-gateway-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "istio-gateway-workspace"
DEPLOYMENT_LABEL = "istio-gateway-deployment"
# The shared host every Deployment's webserver is published under, distinguished by a
# /<release>/airflow path prefix. The per-deployment subdomain below is the second host on the
# same VirtualService -- both are asserted, since they are separate `match` entries and a
# regression can drop one while leaving the other working.
DEPLOYMENTS_HOST = f"deployments.{BASE_DOMAIN}"


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


@pytest.fixture(scope="module")
def _apps_v1_client() -> client.AppsV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def _core_v1_client() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def _houston_api():
    """Houston's own container. GraphQL runs from inside it, because the pytest process has no
    network path into the kind cluster's pod network (see tests/utils/houston_graphql.graphql)."""
    pod = get_pod_by_label_selector(PLATFORM_NAMESPACE, "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={PLATFORM_NAMESPACE}", kubeconfig=KUBECONFIG_UNIFIED)


@pytest.fixture(scope="module")
def airflow_deployment(_houston_api, _apps_v1_client, _core_v1_client):
    """One real Airflow Deployment for the whole module, created through Houston's API.

    Module-scoped because a Deployment is by far the most expensive thing this scenario does;
    every deployment-namespace assertion below reads the same release rather than paying for its
    own. image-based with a LocalExecutor, deliberately the cheapest shape that still renders a
    webserver VirtualService: the CeleryExecutor extras (statsd/pgbouncer/flower/redis) add no
    Istio objects, and this scenario's CI node has to fit the Deployment on top of a platform
    chart whose nginx is off but whose monitoring tier is fully on.

    createUser's unauthenticated signup only succeeds once per cluster, which makes this fixture
    unrunnable twice against the same cluster -- fine in CI (every job builds a fresh one) but
    worth knowing locally, where a second `pytest` run against a surviving cluster fails here
    with "Public sign ups are disabled" until bin/run-scenario.py rebuilds it.
    """
    token = create_user(_houston_api, ADMIN_EMAIL, ADMIN_PASSWORD)
    workspace_id = create_workspace(_houston_api, token, WORKSPACE_LABEL)
    cluster_id = get_cluster_id(_houston_api, token)
    try:
        created = upsert_deployment(
            _houston_api,
            token,
            executor="LocalExecutor",
            label=DEPLOYMENT_LABEL,
            workspace_id=workspace_id,
            cluster_id=cluster_id,
            dag_deployment_type="image",
        )
    except HoustonError:
        # Which side rejected the create is the whole diagnosis: houston-api's own validation, or
        # commander failing to apply the release (the istio RBAC in commander-role.yaml is
        # gateway-gated, so a regression there surfaces as a commander-side failure here).
        dump_pod_logs(_core_v1_client, "component=houston")
        dump_pod_logs(_core_v1_client, "component=commander")
        raise
    release_name = created["releaseName"]
    wait_for_release_ready(_apps_v1_client, _core_v1_client, release_name)
    return {"release_name": release_name, "namespace": f"astronomer-{release_name}"}


def _deployment_virtualservices(custom_objects_client: client.CustomObjectsApi, namespace: str) -> dict:
    """{name: object} for the VirtualServices commander created in a Deployment's namespace."""
    return _list_istio_objects(custom_objects_client, "virtualservices", namespace)


def _get_through_gateway(gateway_port: int, host: str, path: str = "/", allow_redirects: bool = False, timeout: int = 30):
    """GET path through the ingress gateway, routed by the Host header alone."""
    return requests.get(
        f"http://127.0.0.1:{gateway_port}{path}",
        headers={"Host": host},
        allow_redirects=allow_redirects,
        timeout=timeout,
    )


def test_virtualservices_exist(_custom_objects_client):
    """The Istio API server accepted every VirtualService the chart renders, at the chart's
    own apiVersion. An empty or short list here most likely means that apiVersion is no
    longer served, or the install silently skipped these objects."""
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


@pytest.mark.parametrize("component", AUTH_SIDECAR_COMPONENTS)
def test_auth_sidecar_runs_on_the_port_the_gateway_routes_to(k8s_core_v1_client, component):
    """global.authSidecar is a hard precondition of the Gateway, and this is the half of it
    that only a live install can show: the auth proxy is really running, on the port the
    VirtualServices send Gateway traffic to.

    templates/validate-istio-gateway-auth-sidecar.yaml fails the render closed when
    global.istio.gateway.enabled is set without global.authSidecar.enabled -- the Gateway
    terminates platform traffic outside the platform, so the sidecar is the only thing
    authenticating the hosts these VirtualServices publish. That abort is already covered at
    the template level, across every supported k8s version, by
    tests/chart_tests/test_istio_virtualservice.py::test_istio_gateway_requires_auth_sidecar.

    What the guard cannot promise is that the sidecar it forced on is actually serving. It
    only reads two values; it never looks at a pod. An auth-proxy container that is missing
    from the workload, crash-looping, or listening on a port other than the one
    global.authSidecar.port also renders into the VirtualService leaves
    test_admin_ui_virtualservices_route_to_the_auth_sidecar passing against a declared port
    with nothing behind it -- and publishes the component through the Gateway with no
    authentication in front of it. Asserted per component rather than "at least one
    sidecar exists anywhere", so one component losing its proxy cannot hide behind the
    other two.
    """
    pods = k8s_core_v1_client.list_namespaced_pod(
        PLATFORM_NAMESPACE, label_selector=f"release={RELEASE_NAME},component={component}"
    ).items

    assert pods, (
        f"No pod matches release={RELEASE_NAME},component={component} in {PLATFORM_NAMESPACE}, so there "
        f"is nothing for {RELEASE_NAME}-{component}-virtualservice to route to. The Gateway publishes "
        f"this component's host, so an absent workload means that host is served by nothing."
    )

    for pod in pods:
        container = next((c for c in pod.spec.containers if c.name == AUTH_SIDECAR_CONTAINER), None)
        assert container is not None, (
            f"{pod.metadata.name} has no {AUTH_SIDECAR_CONTAINER} container (containers: "
            f"{sorted(c.name for c in pod.spec.containers)}). global.authSidecar.enabled is on in this "
            f"scenario and the Gateway requires it, so this component is reachable through the Gateway "
            f"with nothing authenticating it."
        )

        ports = {port.container_port for port in container.ports or []}
        assert ports == {AUTH_SIDECAR_PORT}, (
            f"{pod.metadata.name}'s {AUTH_SIDECAR_CONTAINER} declares port(s) {sorted(ports)}, not "
            f"global.authSidecar.port ({AUTH_SIDECAR_PORT}). The VirtualServices route to "
            f"{AUTH_SIDECAR_PORT}, so a sidecar listening elsewhere makes this host a 503 through the "
            f"Gateway while every VirtualService still looks correct."
        )

        statuses = {status.name: status for status in pod.status.container_statuses or []}
        sidecar_status = statuses.get(AUTH_SIDECAR_CONTAINER)
        assert sidecar_status is not None and sidecar_status.ready, (
            f"{pod.metadata.name}'s {AUTH_SIDECAR_CONTAINER} is not ready "
            f"(state: {sidecar_status.state if sidecar_status else None}, "
            f"restarts: {sidecar_status.restart_count if sidecar_status else None}). The container is in "
            f"the pod spec but not serving, so the port the Gateway routes to refuses connections."
        )


@pytest.mark.flaky(reruns=10, reruns_delay=6)
@pytest.mark.parametrize("component", AUTH_SIDECAR_COMPONENTS)
def test_gateway_reaches_the_auth_sidecar(gateway_port, component):
    """A real request through the Gateway gets a response FROM the auth proxy.

    The status is deliberately not asserted, because in kind it is a 500: the proxy's own auth
    subrequest targets a public hostname that resolves to loopback inside the pod, so it cannot
    succeed here (see the out-of-scope list in the module docstring). What this asserts instead
    is where the response came from. nginx answering *at all* -- even with its own 500 -- proves
    Envoy matched the host, connected to AUTH_SIDECAR_PORT and was not dropped on the way; the
    statuses that mean it never got there are excluded by GATEWAY_UNREACHED_STATUSES.

    It is also the only coverage of the ADMIN UIs' half of
    global.authSidecar.ingressAllowedNamespaces, which is the likeliest way a real install ends up
    with unreachable UIs while every VirtualService still looks correct. Their NetworkPolicies
    admit AUTH_SIDECAR_PORT only from namespaces labelled
    `network.openshift.io/policy-group: ingress` (an OpenShift convention nothing applies to
    istio-system) plus the namespaces listed in that value (see
    charts/grafana/templates/grafana-networkpolicy.yaml). Verified by removing istio-system from
    the live policy: all three hosts go from 500 in ~0.02s to 503 after a ~30s connect timeout.

    Note the value is NOT only read by these three. astronomer-houston-policy takes the same
    namespaceSelector, so dropping istio-system also makes test_gateway_routes_houston fail --
    this test narrows such a failure to the auth-proxy tier rather than being the sole detector.

    Parametrized over all three components rather than grafana alone -- each has its own
    NetworkPolicy, so one of them losing the allowance is invisible if only another is checked.
    """
    response = _get_through_gateway(gateway_port, f"{component}.{BASE_DOMAIN}", timeout=GATEWAY_UNREACHED_TIMEOUT)

    assert response.status_code not in GATEWAY_UNREACHED_STATUSES, (
        f"GET / through the gateway as {component}.{BASE_DOMAIN} returned {response.status_code}, "
        f"so nothing answered from {component}'s auth proxy. A 404 means Envoy has no route for "
        f"this host, so the VirtualService is not attached to the Gateway this gateway pod serves. "
        f"A 503 or 504 means the route exists but the proxy never answered: either nothing is "
        f"serving port {AUTH_SIDECAR_PORT}, or -- far more likely -- NetworkPolicy is dropping the "
        f"gateway's traffic, so check that global.authSidecar.ingressAllowedNamespaces includes "
        f"{ISTIO_NAMESPACE}. An `upstream connect error ... connection timeout` body is Envoy's, "
        f"not the proxy's, and confirms the drop. Body: {response.text[:300]}"
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


def test_deployment_virtualservice_exists(_custom_objects_client, airflow_deployment):
    """An Airflow Deployment gets a webserver VirtualService in its own namespace.

    This is the commander-metadata -> airflow-chart half of the gateway path, and the only part
    of it this repo can check end to end. The chart's side is just
    charts/astronomer/templates/commander/commander-metadata.yaml writing
    `istio.gateway.{enabled,name}` into commander's metadata ConfigMap, plus the gateway-gated
    networking.istio.io grant in commander-role.yaml; the template that turns that metadata into
    a VirtualService lives in airflow-chart, which this repo does not contain. So nothing here can
    be asserted by rendering -- either commander really created the object against the live Istio
    API or the deployment is published by nothing.
    """
    namespace = airflow_deployment["namespace"]
    found = _deployment_virtualservices(_custom_objects_client, namespace)

    expected = f"{airflow_deployment['release_name']}-webserver-virtualservice"
    assert expected in found, (
        f"{namespace} has no {expected} (found {sorted(found)}). With global.istio.gateway.enabled "
        f"the deployment's webserver should be published by a VirtualService. An empty namespace "
        f"here means commander never created one -- check that commander's metadata ConfigMap still "
        f"carries the istio.gateway block, and that commander-role.yaml still grants "
        f"networking.istio.io/virtualservices."
    )


def test_deployment_virtualservice_hosts(_custom_objects_client, airflow_deployment):
    """The deployment's VirtualService claims both of its published hosts.

    airflow-chart publishes a Deployment two ways on one VirtualService: the shared
    deployments.<baseDomain> host narrowed by a /<release>/airflow URI prefix, and a
    <release>-airflow.<baseDomain> subdomain of its own. Both are asserted because they are
    separate `match` entries -- a regression can drop either while the other keeps working, and
    which one a given install's UI links to is not this scenario's business.
    """
    release_name = airflow_deployment["release_name"]
    virtualservice = _deployment_virtualservices(_custom_objects_client, airflow_deployment["namespace"])[
        f"{release_name}-webserver-virtualservice"
    ]

    expected_hosts = {DEPLOYMENTS_HOST, f"{release_name}-airflow.{BASE_DOMAIN}"}
    assert set(virtualservice["spec"]["hosts"]) == expected_hosts, (
        f"{release_name}'s webserver VirtualService claims hosts {sorted(virtualservice['spec']['hosts'])}, "
        f"not {sorted(expected_hosts)}. These are the hostnames the platform publishes an Airflow "
        f"Deployment on, so a drift here is a real change in its externally reachable surface."
    )

    prefixes = {
        match["uri"]["prefix"]
        for http in virtualservice["spec"].get("http", [])
        for match in http.get("match", [])
        if "uri" in match
    }
    assert f"/{release_name}/airflow" in prefixes, (
        f"{release_name}'s webserver VirtualService has URI prefixes {sorted(prefixes)}, missing "
        f"/{release_name}/airflow. Without it the shared {DEPLOYMENTS_HOST} host cannot tell this "
        f"deployment's traffic from any other deployment's."
    )


def test_deployment_virtualservice_gateway_reference_resolves(_custom_objects_client, airflow_deployment):
    """The deployment's VirtualService attaches to a Gateway that really exists.

    The same silent failure as test_virtualservice_gateway_references_resolve, one layer out: this
    reference is not rendered by this repo's templates but passed through commander's metadata as a
    string, so a wrong namespace or a typo survives all the way to a VirtualService the API server
    accepts and that routes nothing.
    """
    release_name = airflow_deployment["release_name"]
    virtualservice = _deployment_virtualservices(_custom_objects_client, airflow_deployment["namespace"])[
        f"{release_name}-webserver-virtualservice"
    ]

    references = virtualservice["spec"]["gateways"]
    assert references == [f"{ISTIO_NAMESPACE}/{GATEWAY_NAME}"], (
        f"{release_name}'s webserver VirtualService attaches to {references}, not the "
        f"{ISTIO_NAMESPACE}/{GATEWAY_NAME} this scenario created. commander passes this through from "
        f"global.istio.gateway.name verbatim."
    )
    for reference in references:
        namespace, _, gateway_name = reference.partition("/")
        _custom_objects_client.get_namespaced_custom_object(
            group=ISTIO_GROUP, version=ISTIO_VERSION, namespace=namespace, plural="gateways", name=gateway_name
        )


def test_no_deployment_ingresses(_networking_v1_client, airflow_deployment):
    """The Gateway suppresses the Deployment's Ingress too, not just the platform's.

    The deployment-namespace counterpart to test_no_platform_ingresses. Both objects serving the
    same host is the failure mode: airflow-chart has to gate its webserver Ingress on the same flag
    that renders the VirtualService, and nothing in this repo can check that it does.
    """
    namespace = airflow_deployment["namespace"]
    ingresses = _networking_v1_client.list_namespaced_ingress(namespace).items

    names = [ingress.metadata.name for ingress in ingresses]
    assert not names, (
        f"global.istio.gateway.enabled is on, so the Airflow Deployment should have no Ingress, but "
        f"{namespace} has: {sorted(names)}. An Ingress alongside the VirtualService means two objects "
        f"publishing the same host, and with nginx disabled in this scenario the Ingress is dead "
        f"config that still claims it."
    )


def test_deployment_virtualservice_routes_to_the_auth_sidecar(_custom_objects_client, airflow_deployment):
    """The deployment's VirtualService routes to the auth proxy, not straight at the webserver.

    Same reasoning as test_admin_ui_virtualservices_route_to_the_auth_sidecar: with the Gateway
    terminating traffic outside the platform and nginx disabled, the sidecar is the only thing
    authenticating the Airflow UI. A route to the webserver's own port would serve it
    unauthenticated while looking perfectly healthy.
    """
    release_name = airflow_deployment["release_name"]
    virtualservice = _deployment_virtualservices(_custom_objects_client, airflow_deployment["namespace"])[
        f"{release_name}-webserver-virtualservice"
    ]

    ports = {
        route["destination"]["port"]["number"] for http in virtualservice["spec"].get("http", []) for route in http.get("route", [])
    }
    assert ports == {AUTH_SIDECAR_PORT}, (
        f"{release_name}'s webserver VirtualService routes to port(s) {sorted(ports)}, not the auth "
        f"sidecar's {AUTH_SIDECAR_PORT}. Routing straight to the webserver's own port means "
        f"unauthenticated access to the Airflow UI through the Gateway."
    )


# only_rerun, unlike every other flaky mark in this module: a rerun re-invokes the
# module-scoped airflow_deployment fixture, whose create_user call is one-shot per cluster
# (Houston's createUser signup). So a fixture failure retried 10 times reports
# "Public sign ups are disabled" from the LAST attempt and buries the real first failure --
# observed masking a wait_for_release_ready timeout exactly this way. Narrowed to assertion
# failures, which is all this test's own flakiness (istiod's xDS push) ever produces.
@pytest.mark.flaky(reruns=10, reruns_delay=6, only_rerun=["AssertionError"])
@pytest.mark.parametrize("host_form", ["subdomain", "shared-host-with-prefix"])
def test_gateway_routes_the_deployment_webserver(gateway_port, airflow_deployment, host_form):
    """Real HTTP through the Gateway reaches the Deployment's webserver tier.

    The headline assertion for the deployment path, and the reason this scenario creates a real
    Deployment at all: everything above reads objects, and a VirtualService can be perfectly shaped
    while Envoy has no route for it. Both published host forms are driven, since they are separate
    `match` entries on the same object.

    Asserted the same way as test_gateway_reaches_the_auth_sidecar, and for the same reason: the
    route's destination is the auth proxy (see test_deployment_virtualservice_routes_to_the_auth_sidecar),
    whose own auth subrequest cannot succeed in kind, so what is provable is that the response came
    from the proxy rather than from Envoy giving up.
    """
    release_name = airflow_deployment["release_name"]
    if host_form == "subdomain":
        host, path = f"{release_name}-airflow.{BASE_DOMAIN}", "/"
    else:
        host, path = DEPLOYMENTS_HOST, f"/{release_name}/airflow"

    response = _get_through_gateway(gateway_port, host, path=path, timeout=GATEWAY_UNREACHED_TIMEOUT)

    assert response.status_code not in GATEWAY_UNREACHED_STATUSES, (
        f"GET {path} through the gateway as {host} returned {response.status_code}, so nothing "
        f"answered from the deployment's auth proxy. A 404 means Envoy has no route for this host "
        f"and prefix -- the deployment's VirtualService is not attached to the Gateway this gateway "
        f"pod serves, or the {host_form} match entry is gone. A 503 or 504 means the route exists "
        f"but the proxy never answered: nothing serving port {AUTH_SIDECAR_PORT}, or NetworkPolicy "
        f"dropping the gateway's traffic into {airflow_deployment['namespace']}. Body: {response.text[:300]}"
    )
