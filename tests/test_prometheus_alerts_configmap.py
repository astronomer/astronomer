import yaml
from tests.helm_template_generator import render_chart


def process_record(rule):
    """Process a record rule.

    https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/
    """
    assert isinstance(rule.get("expr"), str)
    assert isinstance(rule.get("record"), str)


def process_alert(rule):
    """Process an alert rule.

    https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/
    """
    assert isinstance(rule.get("alert"), str)
    assert isinstance(rule.get("expr"), str)
    if rule["alert"] != "Watchdog":
        assert isinstance(rule.get("for"), str)
    assert isinstance(rule.get("labels"), dict)
    assert isinstance(rule.get("annotations"), dict)


def test_prometheus_alerts_configmap():
    """Validate the prometheus alerts configmap and its embedded data."""
    docs = render_chart(
        show_only=["charts/prometheus/templates/prometheus-alerts-configmap.yaml"],
    )

    assert len(docs) == 1

    doc = docs[0]

    assert doc["kind"] == "ConfigMap"
    assert doc["apiVersion"] == "v1"
    assert doc["metadata"]["name"] == "RELEASE-NAME-prometheus-alerts"

    # Validate the contents of an embedded yaml doc
    groups = yaml.safe_load(doc["data"]["alerts"])["groups"]
    for group in groups:
        assert isinstance(group.get("name"), str)
        assert isinstance(group.get("rules"), list)
        for rule in group["rules"]:
            if rule.get("alert"):
                process_alert(rule)
            else:
                process_record(rule)
