from tests.unit_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
from tests import get_containers_by_name


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonApiDeployment:
    def test_houston_api_deployment(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "Deployment"
        assert "annotations" not in doc["metadata"]
        assert (
            {
                "tier": "astronomer",
                "component": "houston",
                "release": "release-name",
            }
            == doc["spec"]["selector"]["matchLabels"]
            == doc["spec"]["template"]["metadata"]["labels"]
        )

        c_by_name = get_containers_by_name(doc, include_init_containers=True)
        assert c_by_name["houston-bootstrapper"]["image"].startswith(
            "quay.io/astronomer/ap-db-bootstrapper:"
        )
        assert c_by_name["houston"]["image"].startswith(
            "quay.io/astronomer/ap-houston-api:"
        )
        assert c_by_name["wait-for-db"]["image"].startswith(
            "quay.io/astronomer/ap-houston-api:"
        )
