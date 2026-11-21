import base64
import json

import pytest
import yaml

from tests.utils import get_all_features, get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart

CUSTOM_CLUSTER_DOMAIN = "cluster.example.net"


def scenario_values(plane_mode, global_overrides=None, astronomer_overrides=None):
    values = get_all_features()
    values["global"].update(
        {
            "clusterDomain": CUSTOM_CLUSTER_DOMAIN,
            "plane": {"mode": plane_mode, "domainPrefix": "dp01"},
            "postgresqlEnabled": True,
            "istio": {"enabled": True},
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
        scenario_values("unified", global_overrides={"customLogging": {"enabled": False}}),
        {
            "Secret/astronomer-bootstrap",
            "ConfigMap/release-name-houston-config",
            "Deployment/release-name-commander",
            "StatefulSet/release-name-prometheus",
            "Sidecar/default-sidecar-config",
        },
    ),
    "unified-custom-logging": (
        scenario_values("unified"),
        {"Deployment/release-name-commander"},
    ),
    "data": (
        scenario_values("data", global_overrides={"customLogging": {"enabled": False}}),
        {
            "Secret/astronomer-bootstrap",
            "Deployment/release-name-commander",
        },
    ),
    "data-without-domain-prefix": (
        scenario_values(
            "data",
            global_overrides={"customLogging": {"enabled": False}, "plane": {"mode": "data", "domainPrefix": None}},
        ),
        {"Deployment/release-name-commander"},
    ),
    "control": (
        scenario_values("control", global_overrides={"authSidecar": {"enabled": False}}),
        {"ConfigMap/release-name-houston-config"},
    ),
}


@pytest.mark.parametrize("scenario", SCENARIOS.keys())
def test_custom_cluster_domain_replaces_cluster_local_everywhere(scenario):
    values, objects_using_cluster_domain = SCENARIOS[scenario]
    rendered = rendered_text_by_object(values)

    assert [name for name, text in rendered.items() if "cluster.local" in text] == []
    assert {name for name in objects_using_cluster_domain if CUSTOM_CLUSTER_DOMAIN not in rendered.get(name, "")} == set()


def test_yaml_ambiguous_cluster_domain_renders_as_string():
    docs = render_chart(
        values={"global": {"clusterDomain": "true"}},
        show_only=[
            "charts/astronomer/templates/commander/commander-deployment.yaml",
            "charts/astronomer/templates/houston/houston-configmap.yaml",
        ],
    )
    docs_by_kind = {doc["kind"]: doc for doc in docs}

    commander_env = get_env_vars_dict(get_containers_by_name(docs_by_kind["Deployment"])["commander"]["env"])
    houston_config = yaml.safe_load(docs_by_kind["ConfigMap"]["data"]["production.yaml"])

    assert commander_env["COMMANDER_CLUSTER_DOMAIN"] == "true"
    assert houston_config["helm"]["clusterDomain"] == "true"


def test_airflow_operator_manager_receives_cluster_domain():
    docs = render_chart(
        values={"global": {"airflowOperator": {"enabled": True}, "clusterDomain": CUSTOM_CLUSTER_DOMAIN}},
        show_only=["charts/airflow-operator/templates/manager/controller-manager-deployment.yaml"],
        validate_objects=False,
    )

    manager_env = {env["name"]: env.get("value") for env in get_containers_by_name(docs[0])["manager"]["env"]}

    assert manager_env["CLUSTER_DOMAIN"] == CUSTOM_CLUSTER_DOMAIN


def test_airflow_operator_webhook_certificate_uses_cluster_domain():
    docs = render_chart(
        values={
            "global": {"airflowOperator": {"enabled": True}, "clusterDomain": CUSTOM_CLUSTER_DOMAIN},
            "airflow-operator": {"certManager": {"enabled": True}},
        },
        show_only=["charts/airflow-operator/templates/certmanager/serving-cert-certificate.yaml"],
        validate_objects=False,
    )

    assert docs[0]["spec"]["dnsNames"] == [
        "release-name-airflow-operator-webhook-service.default.svc",
        f"release-name-airflow-operator-webhook-service.default.svc.{CUSTOM_CLUSTER_DOMAIN}",
    ]


def test_filesd_reloader_receives_cluster_domain():
    docs = render_chart(
        values={"global": {"clusterDomain": CUSTOM_CLUSTER_DOMAIN}},
        show_only=["charts/prometheus/templates/prometheus-statefulset.yaml"],
        validate_objects=False,
    )

    reloader_env = get_env_vars_dict(get_containers_by_name(docs[0])["filesd-reloader"]["env"])

    assert reloader_env["CLUSTER_DOMAIN"] == CUSTOM_CLUSTER_DOMAIN


@pytest.mark.parametrize("cluster_domain", ["", None])
def test_empty_cluster_domain_is_rejected(cluster_domain):
    with pytest.raises(Exception) as err:
        render_chart(values={"global": {"clusterDomain": cluster_domain}})

    assert "global.clusterDomain must not be empty" in err.value.stderr.decode()
