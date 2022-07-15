from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import jmespath


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPostgresOperator:
    def test_postgres_operator_deployment_defaults(self, kube_version):
        """Test External ElasticSearch with secret passed from config/values.yaml."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"postgresOperatorEnabled": True}},
            show_only=[
                "charts/postgres-operator/templates/postgres-operator-deployment.yaml",
                "charts/postgres-operator/templates/api-service.yaml",
                "charts/postgres-operator/templates/postgres-operator-serviceaccount.yaml",
                "charts/postgres-operator/templates/configmap.yaml",
            ],
        )

        assert len(docs) == 4
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-postgres-operator"
        assert doc["spec"]["template"]["spec"]["containers"][0]["securityContext"] == {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "runAsUser": 1000,
        }
        assert doc["spec"]["template"]["spec"]["containers"][0]["resources"] == {
            "requests": {"cpu": "100m", "memory": "250Mi"},
            "limits": {"cpu": "500m", "memory": "500Mi"},
        }

        assert [
            {
                "name": "CONFIG_MAP_NAME",
                "value": "release-name-postgres-operator-configmap",
            }
        ] in jmespath.search("spec.template.spec.containers[*].env", doc)

        assert "Service" == jmespath.search("kind", docs[1])
        assert "release-name-postgres-operator-service" == jmespath.search(
            "metadata.name", docs[1]
        )
        assert "ClusterIP" == jmespath.search("spec.type", docs[1])
        assert {"protocol": "TCP", "port": 8080, "targetPort": 8080} in jmespath.search(
            "spec.ports", docs[1]
        )
