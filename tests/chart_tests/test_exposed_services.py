"""Cross-cutting guard for everything the chart exposes through an Ingress or an Istio VirtualService.

Two rules, applied to every Ingress and VirtualService in several representative installs:

1. Every exposed backend Service must be on an explicit allowlist, each entry with the reason it is
   safe to expose. A new, unreviewed backend (or a raw ES Service) fails the test, and the author
   has to decide how it is authenticated.
2. Backends that rely on the Ingress for authentication must carry an ``auth-url`` annotation,
   unless the auth sidecar is enabled (then the sidecar is the authenticator, and the Istio gateway
   always requires it).

The allowlist deliberately lists *why* a backend is exposed without ingress-level auth. Do not add a
backend here unless it authenticates every request itself.
"""

import copy
import re

import pytest

from tests import supported_k8s_versions
from tests.utils import get_all_features
from tests.utils.chart import render_chart

RELEASE_PREFIX = "release-name-"

SELF_AUTHENTICATING = {
    "houston": "Houston API: application-level auth on every route",
    "astro-ui": "static UI; every API call it makes is authenticated by Houston",
    "registry": "docker registry: token auth issued by Houston",
    "commander": "gRPC/metadata from the control plane. NOT VERIFIED: owners to confirm mTLS/JWT",
    "laminar-api-server": "NOT VERIFIED: owners to confirm the API authenticates every request",
    "prometheus-prom-proxy": "federation-auth nginx: auth_request to Houston before proxying to Prometheus",
    "external-es-proxy": "nginx: auth_request to Houston, index-scoped. ONLY on its secure port, see EXTERNAL_ES_PROXY_AUTH_PORT",
    "elasticsearch-nginx": "nginx: auth_request to Houston, index-scoped, deny all for other paths",
}

INGRESS_AUTH_REQUIRED = {
    "alertmanager": "no authentication of its own",
    "grafana": "anonymous access is not authentication",
    "prometheus": "no authentication of its own",
}

AUTH_PROXY_CONFIGMAPS = {
    "elasticsearch-nginx": "charts/elasticsearch/templates/nginx/nginx-es-configmap.yaml",
    "external-es-proxy": "charts/external-es-proxy/templates/external-es-proxy-configmap.yaml",
}

# external-es-proxy runs two nginx servers: securehttp (9200) with auth_request, and http (9201) with
# no auth that forwards every path to the customer's external ES with the stored credentials injected.
# 9201 is for in-cluster trusted clients (vector) and must never be what an Ingress targets.
EXTERNAL_ES_PROXY_AUTH_PORT = 9200

# Raw Elasticsearch Services (unauthenticated: xpack security is off). Never expose these.
RAW_ES_SERVICE = re.compile(r"^release-name-elasticsearch(-(client|data|master|headless|exporter))?$")

CUSTOM_LOGGING = {
    "enabled": True,
    "scheme": "https",
    "host": "es.external.example.com",
    "port": 9200,
    "secretName": "es-credentials",
}
ISTIO_GATEWAY = {"enabled": True, "gateway": {"enabled": True, "name": "gw"}}


def _merge(base, extra):
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def _values(mode, **global_overrides):
    return {"global": {"baseDomain": "example.com", "plane": {"mode": mode}, **global_overrides}}


def _all_features(mode):
    return _merge(copy.deepcopy(get_all_features()), _values(mode))


# id -> (values, auth sidecar enabled)
SCENARIOS = {
    "unified": (_values("unified"), False),
    "control": (_values("control"), False),
    "data": (_values("data"), False),
    "data-custom-logging": (_values("data", customLogging=CUSTOM_LOGGING), False),
    "unified-all-features": (_all_features("unified"), None),
    "control-all-features": (_all_features("control"), None),
    "data-all-features": (_all_features("data"), None),
    "unified-istio": (_values("unified", istio=ISTIO_GATEWAY, authSidecar={"enabled": True}), True),
    "data-istio": (_values("data", istio=ISTIO_GATEWAY, authSidecar={"enabled": True}), True),
}


def _exposures(docs):
    """Yield (kind, object name, backend Service name, annotations) for every routed backend."""
    for kind, name, backend, annotations, _ in _exposures_with_port(docs):
        yield kind, name, backend, annotations


def _exposures_with_port(docs):
    """Like _exposures, plus the backend port (number or name) the route targets."""
    for doc in docs:
        if not doc:
            continue
        annotations = doc["metadata"].get("annotations") or {}
        if doc["kind"] == "Ingress":
            for rule in doc["spec"]["rules"]:
                for path in rule["http"]["paths"]:
                    port = path["backend"]["service"]["port"]
                    yield (
                        doc["kind"],
                        doc["metadata"]["name"],
                        path["backend"]["service"]["name"],
                        annotations,
                        port.get("number", port.get("name")),
                    )
        elif doc["kind"] == "VirtualService":
            for http in doc["spec"].get("http", []):
                for route in http.get("route", []):
                    port = route["destination"].get("port", {}).get("number")
                    yield doc["kind"], doc["metadata"]["name"], route["destination"]["host"].split(".")[0], annotations, port


def _sidecar_enabled(values):
    return bool(values["global"].get("authSidecar", {}).get("enabled"))


@pytest.fixture(scope="module", params=sorted(SCENARIOS))
def rendered(request):
    values, _ = SCENARIOS[request.param]
    docs = render_chart(kube_version=supported_k8s_versions[-1], values=values, validate_objects=False)
    return values, [d for d in docs if d and d["kind"] in ("Ingress", "VirtualService")]


def test_scenarios_expose_something(rendered):
    """Guard against the check passing vacuously because nothing was rendered."""
    _, docs = rendered
    assert list(_exposures(docs)), "scenario rendered no Ingress/VirtualService backends"


def test_no_ingress_or_virtualservice_targets_raw_elasticsearch(rendered):
    """No Ingress or VirtualService may route to a raw Elasticsearch Service (it has no authentication); only to an authenticating proxy."""
    _, docs = rendered
    offenders = sorted(
        f"{kind}/{name} -> {backend}" for kind, name, backend, _ in _exposures(docs) if RAW_ES_SERVICE.match(backend)
    )
    assert not offenders, (
        "Ingress/VirtualService routes to an unauthenticated Elasticsearch Service; "
        f"route to the nginx auth proxy (<release>-elasticsearch-nginx) instead: {offenders}"
    )


def test_every_exposed_backend_is_reviewed(rendered):
    """Any Service exposed through an Ingress/VirtualService must be on the reviewed allowlist."""
    _, docs = rendered
    known = set(SELF_AUTHENTICATING) | set(INGRESS_AUTH_REQUIRED)
    unknown = sorted(
        f"{kind}/{name} -> {backend}"
        for kind, name, backend, _ in _exposures(docs)
        if backend.removeprefix(RELEASE_PREFIX) not in known
    )
    assert not unknown, (
        "New externally exposed backend(s). Decide how each is authenticated, then add it to "
        f"SELF_AUTHENTICATING (it authenticates itself) or INGRESS_AUTH_REQUIRED (auth-url): {unknown}"
    )


def test_ingress_auth_required_backends_have_auth_url(rendered):
    """Backends with no auth of their own need auth-url on the Ingress, unless the auth sidecar fronts them."""
    values, docs = rendered
    if _sidecar_enabled(values):
        pytest.skip("auth sidecar enabled: the sidecar authenticates these backends")
    missing = sorted(
        f"{name} -> {backend}"
        for kind, name, backend, annotations in _exposures(docs)
        if kind == "Ingress"
        and backend.removeprefix(RELEASE_PREFIX) in INGRESS_AUTH_REQUIRED
        and not any(key.endswith("/auth-url") for key in annotations)
    )
    assert not missing, f"Ingress has no auth-url annotation but its backend has no authentication of its own: {missing}"


def test_external_es_proxy_is_exposed_on_its_authenticated_port():
    """The external-es-proxy Ingress must target the port that runs auth_request, not the trusted in-cluster one."""
    docs = render_chart(
        kube_version=supported_k8s_versions[-1],
        values=_values("data", customLogging=CUSTOM_LOGGING),
        validate_objects=False,
    )
    wrong = sorted(
        f"{kind}/{name} -> {backend}:{port}"
        for kind, name, backend, _, port in _exposures_with_port(
            d for d in docs if d and d["kind"] in ("Ingress", "VirtualService")
        )
        if backend.removeprefix(RELEASE_PREFIX) == "external-es-proxy" and port != EXTERNAL_ES_PROXY_AUTH_PORT
    )
    assert not wrong, f"external-es-proxy exposed on a port without authentication: {wrong}"


@pytest.mark.parametrize("proxy", sorted(AUTH_PROXY_CONFIGMAPS))
def test_allowlisted_auth_proxies_really_authenticate(proxy):
    """The allowlist claims these proxies authenticate; make sure their config still does."""
    docs = render_chart(
        kube_version=supported_k8s_versions[-1],
        show_only=[AUTH_PROXY_CONFIGMAPS[proxy]],
        values=_values("data", customLogging=CUSTOM_LOGGING) if proxy == "external-es-proxy" else _values("unified"),
        validate_objects=False,
    )
    assert len(docs) == 1
    config = "".join(docs[0]["data"].values())
    assert "auth_request /auth" in config, f"{proxy} no longer authenticates requests with auth_request"
    if proxy == "elasticsearch-nginx":
        assert "deny all" in config, f"{proxy} no longer denies unlisted paths"
