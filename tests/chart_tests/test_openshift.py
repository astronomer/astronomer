import pytest
import jmespath

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart

show_only = [
    "charts/alertmanager/templates/alertmanager-statefulset.yaml",
    "charts/astronomer/templates/registry/registry-statefulset.yaml",
    "charts/elasticsearch/templates/client/es-client-deployment.yaml",
    "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
    "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
    "charts/prometheus-node-exporter/templates/daemonset.yaml",
    "charts/nats/templates/statefulset.yaml",
    "charts/stan/templates/statefulset.yaml",
]


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestOpenshift:
    def test_openshift_flag_defaults_with_enabled_and_validate_podsecuritycontext(
        self, kube_version
    ):
        "Validate podSecurityContext is not set when openshiftEnabled is True"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"openshiftEnabled": True},
            },
            show_only=show_only,
        )

        assert len(docs) == 8
        for doc in docs:
            assert "securityContext" not in doc["spec"]["template"]["spec"]

    def test_openshift_flag_defaults_with_enabled_and_validate_container_securitycontext(
        self, kube_version
    ):
        "Validate containerSecurityContext when openshiftEnabled is Enabled"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"openshiftEnabled": True},
            },
            show_only=[
                "charts/prometheus/templates/prometheus-statefulset.yaml",
                "charts/nats/templates/statefulset.yaml",
                "charts/kibana/templates/kibana-deployment.yaml",
                "charts/elasticsearch/templates/client/es-client-deployment.yaml",
                "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
                "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
            ],
        )

        assert len(docs) == 6
        for doc in docs:
            assert "runAsUser" not in jmespath.search(
                "spec.template.spec.containers[*].securityContext", doc
            )
