import base64
import json

import pytest

from tests.utils import get_all_features
from tests.utils.chart import render_chart

CUSTOM_CLUSTER_DOMAIN = "cluster.example.net"


def scenario_values(plane_mode, global_overrides=None, astronomer_overrides=None):
    values = get_all_features()
    values["global"].update(
        {
            "clusterDomain": CUSTOM_CLUSTER_DOMAIN,
            "plane": {"mode": plane_mode, "domainPrefix": "dp01"},
            "postgresql": {"enabled": True},
            "istio": {"enabled": True, "gateway": {"enabled": True, "name": "istio-gateway"}},
        }
    )
    values["global"].update(global_overrides or {})
    values.setdefault("astronomer", {}).update(astronomer_overrides or {})
    return values


def rendered_text_by_object(values):
    rendered = {}
    for doc in render_chart(values=values, validate_objects=False):
        if doc["kind"] == "Secret" and doc.get("data"):
            doc["data"] = {key: base64.b64decode(value).decode(errors="replace") for key, value in doc["data"].items()}
        name = f"{doc['kind']}/{doc['metadata']['name']}"
        rendered[name] = rendered.get(name, "") + json.dumps(doc)
    return rendered


SCENARIOS = {
    "unified": (
        scenario_values("unified"),
        {
            "Secret/astronomer-bootstrap",
            "ConfigMap/release-name-houston-config",
            "Deployment/release-name-commander",
            "Deployment/release-name-pilot",
            "Certificate/release-name-airflow-operator-serving-cert",
            "Sidecar/default-sidecar-config",
            "VirtualService/release-name-alertmanager-virtualservice",
            "VirtualService/release-name-astroui-virtualservice",
            "VirtualService/release-name-grafana-virtualservice",
            "VirtualService/release-name-houston-virtualservice",
            "VirtualService/release-name-prometheus-virtualservice",
            "VirtualService/release-name-registry-virtualservice",
        },
    ),
    "data": (
        scenario_values("data", global_overrides={"customLogging": {"enabled": False}}),
        {
            "Secret/astronomer-bootstrap",
            "Deployment/release-name-commander",
            "Deployment/release-name-pilot",
            "VirtualService/release-name-commander-api-virtualservice",
            "VirtualService/release-name-commander-metadata-virtualservice",
            "VirtualService/release-name-elasticsearch-virtualservice",
            "VirtualService/release-name-prometheus-federate-virtualservice",
        },
    ),
    "control-mcp-server": (
        scenario_values(
            "control",
            global_overrides={"authSidecar": {"enabled": False}, "istio": {"enabled": True, "gateway": {"enabled": False}}},
            astronomer_overrides={"mcpServer": {"enabled": True}},
        ),
        {
            "ConfigMap/release-name-houston-config",
            "Deployment/release-name-mcp-server",
            "Ingress/release-name-mcp-server-ingress",
        },
    ),
}


@pytest.mark.parametrize("scenario", SCENARIOS.keys())
def test_custom_cluster_domain_replaces_cluster_local_everywhere(scenario):
    values, objects_using_cluster_domain = SCENARIOS[scenario]
    rendered = rendered_text_by_object(values)

    assert [name for name, text in rendered.items() if "cluster.local" in text] == []
    assert {name for name in objects_using_cluster_domain if CUSTOM_CLUSTER_DOMAIN not in rendered.get(name, "")} == set()
