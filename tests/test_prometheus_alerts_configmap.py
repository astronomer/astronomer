import yaml
from tests.helm_template_generator import render_chart
from . import supported_k8s_versions
import re
import pytest


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusAlertConfigmap:
    show_only = ["charts/prometheus/templates/prometheus-alerts-configmap.yaml"]

    @staticmethod
    def process_record(rule):
        """Process a record rule.

        https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/
        """
        assert isinstance(rule.get("expr"), str)
        assert isinstance(rule.get("record"), str)

    @staticmethod
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

    def test_prometheus_alerts_configmap(self, kube_version):
        """Validate the prometheus alerts configmap and its embedded data."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
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
                    self.process_alert(rule)
                else:
                    self.process_record(rule)

    def test_prometheus_alerts_configmap_with_different_name_and_ns(self, kube_version):
        """Validate the prometheus alerts configmap does not conflate helm deployment name and namespace."""
        docs = render_chart(
            name="FOO-NAME",
            namespace="BAR-NS",
            kube_version=kube_version,
            show_only=self.show_only,
        )

        config_yaml = docs[0]["data"]["alerts"]
        assert re.search(r'job="FOO-NAME', config_yaml)
        assert not re.search(r'job="BAR-NS', config_yaml)
        assert re.search(r'namespace="BAR-NS"', config_yaml)
        assert not re.search(r'namespace="FOO-NAME"', config_yaml)

    def test_prometheus_alerts_configmap_with_addition_alerts(self, kube_version):
        """Validate the prometheus alerts configmap renders additional alerts."""

        additional_alerts = {
            "airflow": '- alert: ExampleAirflowAlert\n  expr: 100 * sum(increase(airflow_ti_failures[30m])) / (sum(increase(airflow_ti_failures[30m])) + sum(increase(airflow_ti_successes[30m]))) > 10\n  for: 15m\n  labels:\n    tier: airflow\n  annotations:\n    summary: The Astronomer Helm release {{ .Release.Name }} is failing task instances {{ printf "%q" "{{ printf \\"%.2f\\" $value }}%" }} of the time over the past 30 minutes\n    description: Task instances failing above threshold\n',
            "platform": '- alert: ExamplePlatformAlert\n  expr: count(rate(airflow_scheduler_heartbeat{}[1m]) <= 0) > 2\n  for: 5m\n  labels:\n    tier: platform\n    severity: critical\n  annotations:\n    summary: {{ printf "%q" "{{ $value }} airflow schedulers are not heartbeating" }}\n    description: "If more than 2 Airflow Schedulers are not heartbeating for more than 5 minutes, this alarm fires."\n',
        }

        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="FOO-NAME",
            namespace="BAR-NS",
            values={"prometheus": {"additionalAlerts": additional_alerts}},
        )

        config_yaml = docs[0]["data"]["alerts"]
        assert re.search(
            r'.*The Astronomer Helm release FOO-NAME is failing task instances "{{ printf \\"%.2f\\" \$value }}\%" of the time over the past 30 minutes.*',
            config_yaml,
        )
        assert re.search(
            r".*If more than 2 Airflow Schedulers are not heartbeating for more than 5 minutes, this alarm fires..*",
            config_yaml,
        )
