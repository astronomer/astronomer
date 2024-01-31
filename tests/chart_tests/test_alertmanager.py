import textwrap

import jmespath
import pytest
import yaml

from tests import get_containers_by_name, supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


def test_alertmanager_defaults():
    """Test that alertmanager chart looks sane with defaults."""
    docs = render_chart(
        show_only=["charts/alertmanager/templates/alertmanager-statefulset.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]

    assert doc["kind"] == "StatefulSet"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == "release-name-alertmanager"
    assert doc["spec"]["template"]["spec"]["securityContext"]["fsGroup"] == 65534

    # rfc1918 configs should be absent from default settings
    assert (
        any(
            "--cluster.advertise-address=" in arg
            for args in jmespath.search("spec.template.spec.containers[*].args", doc)
            for arg in args
        )
        is False
    )
    assert [
        value
        for item in jmespath.search(
            "spec.template.spec.containers[*].env[?name == 'POD_IP'].valueFrom.fieldRef.fieldPath",
            doc,
        )
        for value in item
    ] == []


def test_alertmanager_rfc1918():
    """Test rfc1918 features of alertmanager template."""
    docs = render_chart(
        values={"alertmanager": {"enableNonRFC1918": True}},
        show_only=["charts/alertmanager/templates/alertmanager-statefulset.yaml"],
    )
    assert len(docs) == 1
    doc = docs[0]

    assert doc["kind"] == "StatefulSet"
    assert doc["apiVersion"] == "apps/v1"
    assert doc["metadata"]["name"] == "release-name-alertmanager"
    assert doc["spec"]["template"]["spec"]["securityContext"]["fsGroup"] == 65534

    assert any(
        "--cluster.advertise-address=" in arg
        for args in jmespath.search("spec.template.spec.containers[*].args", doc)
        for arg in args
    )
    assert all(
        value
        for item in jmespath.search(
            "spec.template.spec.containers[*].env[?name == 'POD_IP'].valueFrom.fieldRef.fieldPath",
            doc,
        )
        for value in item
    )


def test_alertmanager_customReceiver():
    """Test  alertmanager customer receiver configuration."""
    test_custom_receiver_config = textwrap.dedent(
        """
        alertmanager:
          customReceiver:
          - name: sns-receiver
            sns_configs:
              - api_url: <SNS ENDPOINT>
                subject: '[Alert: {{ .GroupLabels.alertname }} - {{ .Status | toUpper }}{{ if eq .Status "firing" }}:{{ .Alerts.Firing | len }}{{ end }}]'
                topic_arn: <SNS-TOPIC>
                sigv4:
                  region: <REGION>
                  role_arn: <SNS-ROLE>
            """
    )
    values = yaml.safe_load(test_custom_receiver_config)
    docs = render_chart(
        values=values,
        show_only=["charts/alertmanager/templates/alertmanager-configmap.yaml"],
    )
    assert len(docs) == 1
    assert "sns-receiver" in docs[0]["data"]["alertmanager.yaml"]


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_alertmanager_extra_volumes(kube_version):
    test_extra_volumes_config = textwrap.dedent(
        """
        alertmanager:
          extraVolumes:
            - name: webhook-alert-secret
              secret:
                secretName: webhook-alert-secret
          extraVolumeMounts:
            - mountPath: "/var/webhook-alert-secret"
              name: webhook-alert-secret
              readOnly: true
        """
    )
    values = yaml.safe_load(test_extra_volumes_config)
    doc = render_chart(
        kube_version=kube_version,
        values=values,
        show_only=["charts/alertmanager/templates/alertmanager-statefulset.yaml"],
    )[0]

    c_by_name = get_containers_by_name(doc, include_init_containers=False)

    assert "webhook-alert-secret" in [
        x["name"] for x in doc["spec"]["template"]["spec"]["volumes"]
    ]
    assert "webhook-alert-secret" in [
        x["name"] for x in c_by_name["alertmanager"]["volumeMounts"]
    ]
