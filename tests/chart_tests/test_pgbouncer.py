import pytest

from tests import get_containers_by_name, supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPGBouncerDeployment:
    def test_pgbouncer_deployment_default_resources(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"pgbouncer": {"enabled": True}}},
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "Deployment"
        assert doc["metadata"]["name"] == "release-name-pgbouncer"

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["pgbouncer"]
        assert c_by_name["pgbouncer"]["resources"] == {
            "limits": {"cpu": "250m", "memory": "256Mi"},
            "requests": {"cpu": "250m", "memory": "256Mi"},
        }
