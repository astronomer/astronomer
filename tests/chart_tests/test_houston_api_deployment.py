import pytest
import jmespath
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

    def test_houston_api_deployment_private_registry_with_secret_name_undefined(
        self, kube_version
    ):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml"
            ],
            values={
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        # secretName being undefined is the crux of this test
                    }
                }
            },
        )

        assert not jmespath.search("spec.template.spec.imagePullSecrets", docs[0])

    def test_houston_api_deployment_private_registry_with_secret_name_defined(
        self, kube_version
    ):
        secretName = "shhhhh"
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml"
            ],
            values={
                "global": {
                    "privateRegistry": {"enabled": True, "secretName": secretName}
                }
            },
        )
        assert (
            jmespath.search("spec.template.spec.imagePullSecrets[0].name", docs[0])
            == secretName
        )

    def test_houston_api_deployment_with_updates_url_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "updateRuntimeCheck": {"enabled": True},
                        "updateAirflowCheck": {"enabled": True},
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_env = c_by_name["houston"]["env"]
        expected_runtime_env = {
            "name": "HOUSTON_SCRIPT_UPDATE_RUNTIME_SERVICE_URL",
            "value": "https://updates.astronomer.io/astronomer-runtime",
        }
        assert expected_runtime_env in houston_env

        expected_airflow_env = {
            "name": "HOUSTON_SCRIPT_UPDATE_SERVICE_URL",
            "value": "https://updates.astronomer.io/astronomer-certified",
        }

        assert expected_airflow_env in houston_env

    def test_houston_api_deployment_with_updates_url_overrides(self, kube_version):
        CUSTOM_RUNTIME_URL = "https://test.me.io/astronomer-runtime"
        CUSTOM_CERTIFIED_URL = "https://test.me.io/astronomer-certified"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "updateAirflowCheck": {
                            "enabled": True,
                            "url": CUSTOM_CERTIFIED_URL,
                        },
                        "updateRuntimeCheck": {
                            "enabled": True,
                            "url": CUSTOM_RUNTIME_URL,
                        },
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_env = c_by_name["houston"]["env"]

        expected_runtime_env = {
            "name": "HOUSTON_SCRIPT_UPDATE_RUNTIME_SERVICE_URL",
            "value": CUSTOM_RUNTIME_URL,
        }
        assert expected_runtime_env in houston_env

        expected_airflow_env = {
            "name": "HOUSTON_SCRIPT_UPDATE_SERVICE_URL",
            "value": CUSTOM_CERTIFIED_URL,
        }

        assert expected_airflow_env in houston_env

    def test_houston_api_deployment_passing_in_base_houston_host_in_env(
        self, kube_version
    ):
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml"
            ],
        )
        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_env = c_by_name["houston"]["env"]

        expected_env = {
            "name": "HOUSTON__HOST",
            "value": "release-name-houston",
        }
        assert expected_env in houston_env

    def test_houston_env_custom_release_name(self, kube_version):
        """Ensure all houston environment __HOST variables use the custom
        release name."""
        docs = render_chart(
            name="custom-name",
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml"
            ],
        )
        assert all(
            env["value"].startswith("custom-name-")
            for env in docs[0]["spec"]["template"]["spec"]["containers"][0]["env"]
            if "__HOST" in env.get("name") and env.get("value")
        )

    def test_houston_env_validate_mutuable_config(self, kube_version):
        """Ensure houston deployment has mutable config set."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml"
            ],
        )
        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_env = c_by_name["houston"]["env"]

        expected_env = {
            "name": "ALLOW_CONFIG_MUTATIONS",
            "value": "true",
        }
        assert expected_env in houston_env
