from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart
import pytest


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
                    "airflow_operator": {"enabled": True},
                },
            },
            show_only=[
                "charts/airflow-operator/templates/certmanager/selfsigned-issuer.yaml",
                "charts/airflow-operator/templates/certmanager/serving-cert-certificate.yaml",
            ],
        )
        assert len(docs) == 2

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
                    "airflow_operator": {"enabled": True},
                },
            },
            show_only=[
                "charts/airflow-operator/templates/crds/airflow.yaml",
                "charts/airflow-operator/templates/crds/allocator.yaml",
                "charts/airflow-operator/templates/crds/apiserver.yaml",
                "charts/airflow-operator/templates/crds/dagprocessor.yaml",
                "charts/airflow-operator/templates/crds/pgbouncer.yaml",
                "charts/airflow-operator/templates/crds/postgres.yaml",
                "charts/airflow-operator/templates/crds/rbac.yaml",
                "charts/airflow-operator/templates/crds/redis.yaml",
                "charts/airflow-operator/templates/crds/runner.yaml",
                "charts/airflow-operator/templates/crds/scheduler.yaml",
                "charts/airflow-operator/templates/crds/statsd.yaml",
                "charts/airflow-operator/templates/crds/triggerer.yaml",
                "charts/airflow-operator/templates/crds/webserver.yaml",
                "charts/airflow-operator/templates/crds/worker.yaml",
            ],
        )
        assert len(docs) == 14

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
                    "airflow_operator": {"enabled": True},
                },
            },
            show_only=["charts/airflow-operator/templates/secrets/webhooks-tls.yaml"],
        )
        assert len(docs) == 1
        ## add more validations to add cabundle,tlscert,tlskey

    def test_airflow_operator_webhooks(self, kube_version):
        """""Test Airflow Operator Webhook tls""" ""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "airflow_operator": {"enabled": True},
                },
            },
            show_only=[
                "charts/airflow-operator/templates/webhooks/mutating-webhook-configuration.yaml",
                "charts/airflow-operator/templates/webhooks/validating-webhook-configuration.yaml",
            ],
        )
        assert len(docs) == 2
