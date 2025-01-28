from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import git_root_dir
from pathlib import Path


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAirflowOperator:
    def test_airflow_operator_cert_manager(self, kube_version):
        """Test Airflow operator cert manager with flags."""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "airflow-operator": {
                    "certManager": {"enabled": True},
                },
                "global": {
                    "airflowOperator": {"enabled": True},
                },
            },
            show_only=[
                "charts/airflow-operator/templates/certmanager/selfsigned-issuer.yaml",
                "charts/airflow-operator/templates/certmanager/serving-cert-certificate.yaml",
            ],
        )
        assert len(docs) == 2
        assert "Issuer" == docs[0]["kind"]
        assert "Certificate" == docs[1]["kind"]
        assert "cert-manager.io/v1" == docs[0]["apiVersion"]
        assert "cert-manager.io/v1" == docs[1]["apiVersion"]
        assert "release-name-airflow-operator-serving-cert" == docs[1]["metadata"]["name"]
        assert "release-name-airflow-operator-selfsigned-issuer" == docs[0]["metadata"]["name"]

    def test_airflow_operator_crd(self, kube_version):
        """Test Airflow Operator crd template"""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "airflow-operator": {
                    "crd": {"create": True},
                },
                "global": {
                    "airflowOperator": {"enabled": True},
                },
            },
            show_only=sorted(
                [str(x.relative_to(git_root_dir)) for x in Path(f"{git_root_dir}/charts/airflow-operator/templates/crds").glob("*")]
            ),
        )
        assert len(docs) == 14
        for doc in docs:
            assert "apiextensions.k8s.io/v1" == doc["apiVersion"]
            assert "CustomResourceDefinition" == doc["kind"]
            assert "cert-manager.io/inject-ca-from" in doc["metadata"]["annotations"]
            assert "airflow.apache.org" in doc["metadata"]["name"]

    def test_airflow_operator_secret(self, kube_version):
        """""Test Airflow Operator Webhook tls""" ""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "airflow-operator": {
                    "webhooks": {
                        "useCustomTlsCerts": True,
                        "caBundle": "abc123",
                        "tlsCert": "tlscert123",
                        "tlsKey": "tlskey123",
                    },
                },
                "global": {
                    "airflowOperator": {"enabled": True},
                },
            },
            show_only=["charts/airflow-operator/templates/secrets/webhooks-tls.yaml"],
        )

        assert len(docs) == 1
        assert "v1" in docs[0]["apiVersion"]
        assert "Secret" in docs[0]["kind"]
        assert "release-name-webhooks-tls-certs" in docs[0]["metadata"]["name"]
        assert "kubernetes.io/tls" in docs[0]["type"]
        expected_data = {"tls.crt": "dGxzY2VydDEyMw==", "tls.key": "dGxza2V5MTIz"}
        assert docs[0]["data"] == expected_data

    def test_airflow_operator_webhooks(self, kube_version):
        """""Test Airflow Operator Webhook tls""" ""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "airflowOperator": {"enabled": True},
                },
            },
            show_only=[
                "charts/airflow-operator/templates/webhooks/mutating-webhook-configuration.yaml",
                "charts/airflow-operator/templates/webhooks/validating-webhook-configuration.yaml",
            ],
        )
        assert len(docs) == 2
        assert "admissionregistration.k8s.io/v1" == docs[0]["apiVersion"]
        assert "MutatingWebhookConfiguration" == docs[0]["kind"]
        assert "ValidatingWebhookConfiguration" == docs[1]["kind"]
        assert "release-name-airflow-operator-mutating-webhook-configuration" == docs[0]["metadata"]["name"]
        assert "release-name-airflow-operator-validating-webhook-configuration" == docs[1]["metadata"]["name"]
