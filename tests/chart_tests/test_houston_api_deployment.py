import pytest

from tests import get_containers_by_name
from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


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
        assert {
            "tier": "astronomer",
            "component": "houston",
            "release": "release-name",
        } == doc["spec"]["selector"]["matchLabels"]

        assert doc["spec"]["template"]["metadata"]["labels"].get("app") == "houston"
        assert doc["spec"]["template"]["metadata"]["labels"].get("app") == "houston"
        assert doc["spec"]["template"]["metadata"]["labels"].get("tier") == "astronomer"
        assert (
            doc["spec"]["template"]["metadata"]["labels"].get("release")
            == "release-name"
        )

        labels = doc["spec"]["template"]["metadata"]["labels"]
        assert {
            "tier": "astronomer",
            "component": "houston",
            "release": "release-name",
            "app": "houston",
        } == {x: labels[x] for x in labels if x != "version"}

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
        houston_env = c_by_name["houston"]["env"]
        deployments_database_connection_env = next(
            x for x in houston_env if x["name"] == "DEPLOYMENTS__DATABASE__CONNECTION"
        )
        assert deployments_database_connection_env is not None

    def test_houston_api_deployment_with_helm_set_database(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml"
            ],
            values={
                "astronomer": {
                    "houston": {
                        "config": {
                            "deployments": {
                                "database": {"connection": {"host": "1.1.1.1"}}
                            }
                        }
                    }
                }
            },
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=True)
        houston_env = c_by_name["houston"]["env"]

        deployments_database_connection_env = next(
            (
                x
                for x in houston_env
                if x["name"] == "DEPLOYMENTS__DATABASE__CONNECTION"
            ),
            None,
        )
        assert deployments_database_connection_env is None
