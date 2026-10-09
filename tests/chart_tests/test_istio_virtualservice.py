"""Tests for the Istio Gateway VirtualService templates.

When `global.istio.gateway.enabled` is set, the nginx Ingress objects are suppressed and these
VirtualServices route the same hosts to the same backends instead.

The key gate difference from the Ingress path: `global.perHostIngress` chooses between one Ingress
object per host and a single Ingress carrying every host, which only matters to nginx annotations.
A VirtualService is per-host by nature, so the VirtualServices replace *both* nginx layouts and must
render regardless of that flag — otherwise the default `perHostIngress: false` leaves app.<baseDomain>
and registry.<baseDomain> with no route at all under Istio.

`global.ingress.enabled` *is* honoured (it gates every Ingress and every VirtualService alike), so
setting it false suppresses all four VirtualServices — see test_no_virtualservices_when_ingress_disabled.
"""

import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

ASTRO_UI_VS = "charts/astronomer/templates/astro-ui/astro-ui-virtualservice.yaml"
HOUSTON_VS = "charts/astronomer/templates/houston/houston-virtualservice.yaml"
REGISTRY_VS = "charts/astronomer/templates/registry/registry-virtualservice.yaml"
COMMANDER_GRPC_VS = "charts/astronomer/templates/commander/commander-grpc-virtualservice.yaml"
COMMANDER_METADATA_VS = "charts/astronomer/templates/commander/commander-metadata-virtualservice.yaml"
ALERTMANAGER_VS = "charts/alertmanager/templates/alertmanager-virtualservice.yaml"
ELASTICSEARCH_VS = "charts/elasticsearch/templates/es-virtualservice.yaml"
GRAFANA_VS = "charts/grafana/templates/grafana-virtualservice.yaml"
PROMETHEUS_VS = "charts/prometheus/templates/prometheus-virtualservice.yaml"
PROMETHEUS_FEDERATE_VS = "charts/prometheus/templates/prometheus-federate-virtualservice.yaml"

BASE_DOMAIN = "example.com"
GLOBAL_BASE_DOMAIN = "astro.example.com"
GATEWAY = "istio-system/default-gateway"

# VirtualServices expected on a control/unified plane, and the host each one serves.
CONTROL_PLANE_VS_HOSTS = {
    "release-name-astroui-virtualservice": [f"app.{BASE_DOMAIN}"],
    "release-name-common-virtualservice": [BASE_DOMAIN],
    "release-name-houston-virtualservice": [f"houston.{BASE_DOMAIN}"],
    "release-name-registry-virtualservice": [f"registry.{BASE_DOMAIN}"],
    "release-name-alertmanager-virtualservice": [f"alertmanager.{BASE_DOMAIN}"],
    "release-name-elasticsearch-virtualservice": [f"elasticsearch.{BASE_DOMAIN}"],
    "release-name-grafana-virtualservice": [f"grafana.{BASE_DOMAIN}"],
    "release-name-prometheus-virtualservice": [f"prometheus.{BASE_DOMAIN}"],
}

ALL_VS_FILES = [
    ASTRO_UI_VS,
    HOUSTON_VS,
    REGISTRY_VS,
    COMMANDER_GRPC_VS,
    COMMANDER_METADATA_VS,
    ALERTMANAGER_VS,
    ELASTICSEARCH_VS,
    GRAFANA_VS,
    PROMETHEUS_VS,
    PROMETHEUS_FEDERATE_VS,
]


def _istio_values(plane_mode="unified", per_host_ingress=None, **global_overrides):
    values = {
        "global": {
            "istio": {"gateway": {"enabled": True, "name": GATEWAY}},
            "nginx": {"enabled": False},
            "plane": {"mode": plane_mode},
            "baseDomain": BASE_DOMAIN,
            **global_overrides,
        }
    }
    if per_host_ingress is not None:
        values["global"]["perHostIngress"] = {"enabled": per_host_ingress}
    return values


def _virtualservices(docs):
    return {doc["metadata"]["name"]: doc for doc in docs if doc and doc.get("kind") == "VirtualService"}


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
@pytest.mark.parametrize("per_host_ingress", [None, False, True], ids=["default", "false", "true"])
def test_control_plane_virtualservices_ignore_per_host_ingress(kube_version, per_host_ingress):
    """Every customer-facing VirtualService renders for any value of global.perHostIngress.

    Regression guard: astro-ui and registry were gated on `perHostIngress.enabled`, whose default is
    false, so an Istio install rendered only the houston VirtualService.
    """
    docs = render_chart(
        kube_version=kube_version,
        show_only=ALL_VS_FILES,
        values=_istio_values(per_host_ingress=per_host_ingress),
    )
    rendered = _virtualservices(docs)
    assert set(rendered) == set(CONTROL_PLANE_VS_HOSTS)
    for name, expected_hosts in CONTROL_PLANE_VS_HOSTS.items():
        assert rendered[name]["spec"]["hosts"] == expected_hosts
        assert rendered[name]["spec"]["gateways"] == [GATEWAY]


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_no_virtualservices_when_ingress_disabled(kube_version):
    """global.ingress.enabled=false suppresses the VirtualServices, not just the Ingress objects.

    That flag is the master switch for all chart-managed north-south routing, so an Istio install
    that sets it false gets no routing at all. Operators who want Istio must leave it unset (it
    defaults true) and select Istio with global.istio.gateway.enabled.
    """
    values = _istio_values()
    values["global"]["ingress"] = {"enabled": False}
    docs = render_chart(kube_version=kube_version, show_only=ALL_VS_FILES, values=values)
    assert _virtualservices(docs) == {}


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_astro_ui_and_registry_route_to_their_services(kube_version):
    """The astro-ui and registry VirtualServices point at the same backends as their Ingresses."""
    rendered = _virtualservices(
        render_chart(kube_version=kube_version, show_only=[ASTRO_UI_VS, REGISTRY_VS], values=_istio_values())
    )

    astro_ui_route = rendered["release-name-astroui-virtualservice"]["spec"]["http"][0]["route"][0]["destination"]
    assert astro_ui_route["host"] == "release-name-astro-ui.default.svc.cluster.local"
    assert astro_ui_route["port"]["number"] == 8080

    registry_route = rendered["release-name-registry-virtualservice"]["spec"]["http"][0]["route"][0]["destination"]
    assert registry_route["host"] == "release-name-registry.default.svc.cluster.local"
    assert registry_route["port"]["number"] == 5000


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_common_virtualservice_redirects_bare_domain(kube_version):
    """The bare base domain 301-redirects to app.<baseDomain>, replacing the nginx rewrite snippet."""
    rendered = _virtualservices(render_chart(kube_version=kube_version, show_only=[ASTRO_UI_VS], values=_istio_values()))
    routes = rendered["release-name-common-virtualservice"]["spec"]["http"]
    assert len(routes) == 1
    assert routes[0]["redirect"] == {
        "authority": f"app.{BASE_DOMAIN}",
        "scheme": "https",
        "redirectCode": 301,
    }


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_astro_ui_virtualservices_ha_hosts(kube_version):
    """HA on: the global customer-facing host family renders alongside the per-CP family.

    Parity with the combined ingress.yaml, which emits <globalBaseDomain> and app.<globalBaseDomain>
    when controlPlaneHA is enabled on a control/unified plane.
    """
    values = _istio_values(controlPlaneHA={"enabled": True, "globalBaseDomain": GLOBAL_BASE_DOMAIN})
    rendered = _virtualservices(render_chart(kube_version=kube_version, show_only=[ASTRO_UI_VS], values=values))

    assert rendered["release-name-astroui-virtualservice"]["spec"]["hosts"] == [
        f"app.{BASE_DOMAIN}",
        f"app.{GLOBAL_BASE_DOMAIN}",
    ]

    common = rendered["release-name-common-virtualservice"]["spec"]
    assert common["hosts"] == [BASE_DOMAIN, GLOBAL_BASE_DOMAIN]
    # Each bare host redirects to app.<that same host>, so the global host needs an authority match
    # ahead of the unmatched baseDomain catch-all.
    assert common["http"][0]["match"] == [{"authority": {"exact": GLOBAL_BASE_DOMAIN}}]
    assert common["http"][0]["redirect"]["authority"] == f"app.{GLOBAL_BASE_DOMAIN}"
    assert "match" not in common["http"][1]
    assert common["http"][1]["redirect"]["authority"] == f"app.{BASE_DOMAIN}"


# The forward-auth admin UIs: (template, subdomain, service name, own port). Their Ingresses swap the
# backend port for the auth sidecar's when it is enabled, and each serves a second host under CP HA.
AUTH_SIDECAR_SERVICES = [
    pytest.param(ALERTMANAGER_VS, "alertmanager", "release-name-alertmanager", 9093, id="alertmanager"),
    pytest.param(GRAFANA_VS, "grafana", "release-name-grafana", 3000, id="grafana"),
    pytest.param(PROMETHEUS_VS, "prometheus", "release-name-prometheus", 9090, id="prometheus"),
]
AUTH_SIDECAR_PORT = 8084


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
@pytest.mark.parametrize("auth_sidecar", [False, True], ids=["auth-sidecar-off", "auth-sidecar-on"])
@pytest.mark.parametrize("vs_file,subdomain,service,own_port", AUTH_SIDECAR_SERVICES)
def test_admin_ui_virtualservice_backend_port(kube_version, auth_sidecar, vs_file, subdomain, service, own_port):
    """The backend port follows global.authSidecar.enabled, exactly as the Ingress backend does.

    With the sidecar on, traffic must enter through its auth-proxy port (global.authSidecar.port)
    rather than the service's own port, or auth is bypassed.
    """
    values = _istio_values()
    if auth_sidecar:
        values["global"]["authSidecar"] = {"enabled": True}
    rendered = _virtualservices(render_chart(kube_version=kube_version, show_only=[vs_file], values=values))
    destination = rendered[f"{service}-virtualservice"]["spec"]["http"][0]["route"][0]["destination"]
    assert destination["host"] == f"{service}.default.svc.cluster.local"
    assert destination["port"]["number"] == (AUTH_SIDECAR_PORT if auth_sidecar else own_port)


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
@pytest.mark.parametrize("vs_file,subdomain,service,own_port", AUTH_SIDECAR_SERVICES)
def test_admin_ui_virtualservice_ha_hosts(kube_version, vs_file, subdomain, service, own_port):
    """HA on: the global customer-facing host renders alongside the per-CP one, as in the Ingress."""
    values = _istio_values(controlPlaneHA={"enabled": True, "globalBaseDomain": GLOBAL_BASE_DOMAIN})
    rendered = _virtualservices(render_chart(kube_version=kube_version, show_only=[vs_file], values=values))
    assert rendered[f"{service}-virtualservice"]["spec"]["hosts"] == [
        f"{subdomain}.{BASE_DOMAIN}",
        f"{subdomain}.{GLOBAL_BASE_DOMAIN}",
    ]


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_data_plane_virtualservices(kube_version):
    """A data plane emits the commander and logging VirtualServices and none of the CP-only ones.

    Elasticsearch is gated on the logging.enabled helper rather than plane.mode, and with
    sharedElasticsearch off the data plane runs its own logging stack — so it renders here.
    """
    values = _istio_values(plane_mode="data")
    values["global"]["plane"]["domainPrefix"] = "dp"
    rendered = _virtualservices(render_chart(kube_version=kube_version, show_only=ALL_VS_FILES, values=values))
    assert set(rendered) == {
        "release-name-commander-api-virtualservice",
        "release-name-commander-metadata-virtualservice",
        "release-name-registry-virtualservice",
        "release-name-elasticsearch-virtualservice",
        "release-name-prometheus-virtualservice",
        "release-name-prometheus-federate-virtualservice",
    }
    assert rendered["release-name-commander-api-virtualservice"]["spec"]["hosts"] == [f"commander.dp.{BASE_DOMAIN}"]
    assert rendered["release-name-registry-virtualservice"]["spec"]["hosts"] == [f"registry.dp.{BASE_DOMAIN}"]
    # The elasticsearch.ingressurl helper prefixes the data-plane domain, as it does for the Ingress.
    assert rendered["release-name-elasticsearch-virtualservice"]["spec"]["hosts"] == [f"elasticsearch.dp.{BASE_DOMAIN}"]
    assert rendered["release-name-prometheus-virtualservice"]["spec"]["hosts"] == [f"prometheus.dp.{BASE_DOMAIN}"]
    assert rendered["release-name-prometheus-federate-virtualservice"]["spec"]["hosts"] == [f"prom-proxy.dp.{BASE_DOMAIN}"]


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_prometheus_data_plane_requires_domain_prefix(kube_version):
    """On a data plane the prometheus VirtualService needs plane.domainPrefix, as its Ingress does.

    Without it prometheus.url would collide with the control plane's own prometheus host.
    """
    values = _istio_values(plane_mode="data")
    docs = render_chart(kube_version=kube_version, show_only=ALL_VS_FILES, values=values)
    assert "release-name-prometheus-virtualservice" not in _virtualservices(docs)


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_prometheus_data_plane_ha_omits_global_host(kube_version):
    """The global customer-facing host is control-plane-only, mirroring $emitGlobalHost in the Ingress.

    globalBaseDomain is set on data planes too under HA, so the plane.mode half of that guard is what
    keeps a data plane from claiming prometheus.<globalBaseDomain>.
    """
    values = _istio_values(plane_mode="data", controlPlaneHA={"enabled": True, "globalBaseDomain": GLOBAL_BASE_DOMAIN})
    values["global"]["plane"]["domainPrefix"] = "dp"
    rendered = _virtualservices(render_chart(kube_version=kube_version, show_only=[PROMETHEUS_VS], values=values))
    assert rendered["release-name-prometheus-virtualservice"]["spec"]["hosts"] == [f"prometheus.dp.{BASE_DOMAIN}"]


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_prometheus_federate_virtualservice_route(kube_version):
    """Federate routes to the prom-proxy federation-auth Service, which is data-plane only.

    That Service *is* the auth proxy, so this route is authenticated regardless of
    global.authSidecar.enabled — unlike the prometheus, grafana and alertmanager routes.
    """
    values = _istio_values(plane_mode="data")
    values["global"]["plane"]["domainPrefix"] = "dp"
    rendered = _virtualservices(
        render_chart(kube_version=kube_version, show_only=[PROMETHEUS_FEDERATE_VS], values=values)
    )
    destination = rendered["release-name-prometheus-federate-virtualservice"]["spec"]["http"][0]["route"][0][
        "destination"
    ]
    assert destination["host"] == "release-name-prometheus-prom-proxy.default.svc.cluster.local"
    assert destination["port"]["number"] == 8084


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_elasticsearch_virtualservice_route(kube_version):
    """Backend and timeout match es-ingress.yaml.

    The Ingress sets proxy-read-timeout/proxy-send-timeout to 300s. Istio's default route timeout is
    15s, so the timeout has to be templated explicitly or long log queries would break under Istio
    while working under nginx.
    """
    rendered = _virtualservices(
        render_chart(kube_version=kube_version, show_only=[ELASTICSEARCH_VS], values=_istio_values())
    )
    route = rendered["release-name-elasticsearch-virtualservice"]["spec"]["http"][0]
    assert route["timeout"] == "300s"
    assert route["route"][0]["destination"]["host"] == "release-name-elasticsearch.default.svc.cluster.local"
    assert route["route"][0]["destination"]["port"]["number"] == 9200


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
@pytest.mark.parametrize(
    "plane_mode,shared_es,custom_logging,expected",
    [
        ("unified", False, False, True),
        ("unified", False, True, False),
        ("control", False, False, False),
        ("control", True, False, True),
        ("data", False, False, True),
        ("data", True, False, False),
    ],
    ids=["unified", "unified-customLogging", "control", "control-shared", "data", "data-shared"],
)
def test_elasticsearch_virtualservice_logging_gates(kube_version, plane_mode, shared_es, custom_logging, expected):
    """Renders exactly when the logging.enabled helper is true and customLogging is off."""
    values = _istio_values(plane_mode=plane_mode)
    values["global"]["sharedElasticsearch"] = {"enabled": shared_es}
    values["global"]["customLogging"] = {"enabled": custom_logging}
    if plane_mode == "data":
        values["global"]["plane"]["domainPrefix"] = "dp"
    docs = render_chart(kube_version=kube_version, show_only=ALL_VS_FILES, values=values)
    assert ("release-name-elasticsearch-virtualservice" in _virtualservices(docs)) is expected


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_no_virtualservices_without_istio_gateway(kube_version):
    """istio.gateway disabled: no VirtualService renders, whatever perHostIngress says."""
    for per_host_ingress in (False, True):
        values = {
            "global": {
                "plane": {"mode": "unified"},
                "baseDomain": BASE_DOMAIN,
                "perHostIngress": {"enabled": per_host_ingress},
            }
        }
        docs = render_chart(kube_version=kube_version, show_only=ALL_VS_FILES, values=values)
        assert _virtualservices(docs) == {}
