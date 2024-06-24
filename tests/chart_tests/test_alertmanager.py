import textwrap

import jmespath
import pytest
import yaml

from tests import get_containers_by_name, supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAlertmanager:
    def test_alertmanager_defaults(self, kube_version):
        """Test that alertmanager chart looks sane with defaults."""
        docs = render_chart(
            kube_version=kube_version,
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
                for args in jmespath.search(
                    "spec.template.spec.containers[*].args", doc
                )
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

    def test_alertmanager_rfc1918(self, kube_version):
        """Test rfc1918 features of alertmanager template."""
        docs = render_chart(
            kube_version=kube_version,
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

    def test_alertmanager_customReceiver(self, kube_version):
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
            kube_version=kube_version,
            values=values,
            show_only=["charts/alertmanager/templates/alertmanager-configmap.yaml"],
        )
        assert len(docs) == 1
        assert "sns-receiver" in docs[0]["data"]["alertmanager.yaml"]

    def test_alertmanager_extra_volumes(self, kube_version):
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

    def test_alertmanager_global_private_ca(self, kube_version):
        values = {
            "global": {
                "privateCaCerts": [
                    "private-ca-cert-foo",
                    "private-ca-cert-bar",
                ],
            },
        }
        doc = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/alertmanager/templates/alertmanager-statefulset.yaml"],
        )[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=False)

        volumemounts = c_by_name["alertmanager"]["volumeMounts"]
        volumes = doc["spec"]["template"]["spec"]["volumes"]

        expected_volumes = [
            {
                "name": "config-volume",
                "configMap": {
                    "name": "release-name-alertmanager",
                    "items": [
                        {"key": "alertmanager.yaml", "path": "alertmanager.yaml"}
                    ],
                },
            },
            {
                "name": "private-ca-cert-foo",
                "secret": {"secretName": "private-ca-cert-foo"},
            },
            {
                "name": "private-ca-cert-bar",
                "secret": {"secretName": "private-ca-cert-bar"},
            },
        ]

        expected_volumemounts = [
            {"name": "config-volume", "mountPath": "/etc/config"},
            {"name": "data", "mountPath": "/data"},
            {
                "name": "private-ca-cert-foo",
                "mountPath": "/usr/local/share/ca-certificates/private-ca-cert-foo.pem",
                "subPath": "cert.pem",
            },
            {
                "name": "private-ca-cert-bar",
                "mountPath": "/usr/local/share/ca-certificates/private-ca-cert-bar.pem",
                "subPath": "cert.pem",
            },
        ]

        assert volumemounts == expected_volumemounts
        assert volumes == expected_volumes
        assert {"name": "UPDATE_CA_CERTS", "value": "true"} in c_by_name[
            "alertmanager"
        ]["env"]
