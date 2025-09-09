import jmespath
import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

show_only = [
    "charts/alertmanager/templates/alertmanager-statefulset.yaml",
    "charts/astronomer/templates/registry/registry-statefulset.yaml",
    "charts/elasticsearch/templates/client/es-client-deployment.yaml",
    "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
    "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
    "charts/nats/templates/statefulset.yaml"
]

airflow_components_list = [
    "flower",
    "webserver",
    "scheduler",
    "workers",
    "redis",
    "triggerer",
    "migrateDatabaseJob",
    "cleanup",
    "dagProcessor",
]


non_airflow_components_list = [
    "statsd",
    "pgbouncer",
]


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestOpenshift:
    def test_openshift_flag_defaults_with_enabled_and_validate_podsecuritycontext(self, kube_version):
        "Validate podSecurityContext is not set when openshiftEnabled is True"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"openshiftEnabled": True},
            },
            show_only=show_only,
        )

        assert len(docs) == 7
        for doc in docs:
            assert "securityContext" not in doc["spec"]["template"]["spec"]

    def test_openshift_flag_defaults_with_enabled_and_validate_container_securitycontext(self, kube_version):
        "Validate containerSecurityContext when openshiftEnabled is Enabled"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"openshiftEnabled": True},
            },
            show_only=[
                "charts/prometheus/templates/prometheus-statefulset.yaml",
                "charts/nats/templates/statefulset.yaml",
                "charts/elasticsearch/templates/client/es-client-deployment.yaml",
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
            ],
        )

        assert len(docs) == 5
        for doc in docs:
            assert "runAsUser" not in jmespath.search("spec.template.spec.containers[*].securityContext", doc)

    def test_openshift_flag_defaults_with_enabled_and_validate_houston_configmap(self, kube_version):
        "Validate houston config when openshiftEnabled is Enabled"
        docs = render_chart(
            values={
                "global": {"openshiftEnabled": True},
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])

        airflowConfig = prod["deployments"]["helm"]["airflow"]

        for component in airflow_components_list:
            assert {"runAsNonRoot": True} == airflowConfig[component]["securityContexts"]["pod"]

        for component in non_airflow_components_list:
            assert {"runAsNonRoot": True} == airflowConfig[component]["securityContexts"]["pod"]

        gitSyncConfig = airflowConfig["dags"]["gitSync"]
        assert {"runAsNonRoot": True} == gitSyncConfig["securityContexts"]["container"]
