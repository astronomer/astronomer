from pathlib import Path

import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


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
            show_only=sorted(
                [
                    str(x.relative_to(git_root_dir))
                    for x in Path(f"{git_root_dir}/charts/airflow-operator/templates/certmanager").glob("*")
                ]
            ),
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
        """Test Airflow Operator Webhook tls"""
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
        """Test Airflow Operator Webhook tls"""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "airflowOperator": {"enabled": True},
                },
                "airflow-operator": {"webhooks": {"enabled": True}},
            },
            show_only=sorted(
                [
                    str(x.relative_to(git_root_dir))
                    for x in Path(f"{git_root_dir}/charts/airflow-operator/templates/webhooks").glob("*")
                ]
            ),
        )
        assert len(docs) == 2
        assert "admissionregistration.k8s.io/v1" == docs[0]["apiVersion"]
        assert "MutatingWebhookConfiguration" == docs[0]["kind"]
        assert "ValidatingWebhookConfiguration" == docs[1]["kind"]
        assert "release-name-airflow-operator-mutating-webhook-configuration" == docs[0]["metadata"]["name"]
        assert "release-name-airflow-operator-validating-webhook-configuration" == docs[1]["metadata"]["name"]

    def test_airflow_operator_airgap(self, kube_version):
        """""Test Airflow Operator airgapped mode""" ""
        runtime_releases_json = {
            "runtimeVersions": {
                "4.2.5": {"metadata": {"airflowVersion": "2.4.2", "channel": "stable", "releaseDate": "2023-01-15"}},
                "5.0.0": {"metadata": {"airflowVersion": "2.5.0", "channel": "stable", "releaseDate": "2023-03-20"}},
            }
        }
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "airflowOperator": {"enabled": True},
                },
                "airflow-operator": {"airgapped": True, "runtimeVersions": {"versionsJson": runtime_releases_json}},
            },
            show_only=["charts/airflow-operator/templates/configmap/runtime-versions.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["apiVersion"] == "v1"
        assert doc["data"]["versions.json"] == runtime_releases_json
        assert doc["kind"] == "ConfigMap"
        assert doc["metadata"]["name"] == "release-name-runtime-version-config"
        assert doc["metadata"]["labels"]["tier"] == "operator"

    def test_airflow_operator_manager_defaults(self, kube_version):
        """Test Airflow Operator manager defaults"""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "airflowOperator": {"enabled": True},
                },
                "airflow-operator": {
                    "manager": {
                        "metrics": {
                            "enabled": True,
                        }
                    },
                    "webhooks": {"enabled": True},
                },
            },
            show_only=sorted(
                [
                    str(x.relative_to(git_root_dir))
                    for x in Path(f"{git_root_dir}/charts/airflow-operator/templates/manager").glob("*")
                ]
            ),
        )
        assert len(docs) == 4
        assert docs[0]["apiVersion"] == "apps/v1"
        assert docs[0]["kind"] == "Deployment"
        assert docs[0]["metadata"]["name"] == "release-name-aocm"
        assert all(doc["metadata"]["labels"]["component"] == "controller-manager" for doc in docs[:3])
        assert all(doc["apiVersion"] == "v1" for doc in docs[1:4])
        assert docs[1]["kind"] == "Service"
        assert docs[1]["metadata"]["name"] == "release-name-aocm-metrics-service"
        assert docs[2]["kind"] == "ConfigMap"
        assert docs[2]["metadata"]["name"] == "release-name-aom-config"
        assert docs[3]["kind"] == "Service"
        assert docs[3]["metadata"]["name"] == "release-name-airflow-operator-webhook-service"

        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "airflowOperator": {"enabled": True},
                },
                "airflow-operator": {
                    "webhooks": {"enabled": False},
                },
            },
            show_only=sorted(
                [
                    str(x.relative_to(git_root_dir))
                    for x in Path(f"{git_root_dir}/charts/airflow-operator/templates/manager").glob("*")
                ]
            ),
        )
        webhook_services = [doc for doc in docs if "webhook" in doc.get("metadata", {}).get("name", "")]
        assert len(webhook_services) == 0

    def test_airflow_operator_manager_metrics_enabled(self, kube_version):
        """Test Airflow Operator manager with metrics endpoints enabled"""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "airflowOperator": {"enabled": True},
                },
                "airflow-operator": {
                    "manager": {
                        "metrics": {
                            "enabled": True,
                        }
                    }
                },
            },
            show_only=[
                "charts/airflow-operator/templates/manager/controller-manager-deployment.yaml",
                "charts/airflow-operator/templates/manager/controller-manager-metrics-service.yaml",
            ],
        )
        assert len(docs) == 2
        c_by_name = get_containers_by_name(docs[0], include_init_containers=False)
        assert "manager" in c_by_name["manager"]["name"]
        assert "--metrics-bind-address=127.0.0.1:8080" in c_by_name["manager"]["args"]
        assert "/manager" in c_by_name["manager"]["command"]
        doc = docs[1]
        assert doc["kind"] == "Service"
        assert doc["metadata"]["name"] == "release-name-aocm-metrics-service"
        assert doc["spec"]["selector"]["component"] == "controller-manager"
        assert doc["spec"]["type"] == "ClusterIP"
        assert doc["spec"]["ports"] == [
            {
                "port": 8443,
                "targetPort": 8080,
                "protocol": "TCP",
                "name": "metrics",
                "appProtocol": "http",
            }
        ]
