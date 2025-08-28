import jmespath
import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonApiDeployment:
    def test_houston_api_deployment_defaults(self, kube_version):
        """Test the default configuration of the Houston API deployment."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
        )

        assert len(docs) == 1
        houston_deployment = docs[0]
        assert houston_deployment["kind"] == "Deployment"
        assert "annotations" not in houston_deployment["metadata"]
        assert houston_deployment["spec"]["selector"]["matchLabels"] == {
            "tier": "astronomer",
            "component": "houston",
            "release": "release-name",
        }

        # Ensure the first dict is contained within the larger labels dict
        assert {
            "tier": "astronomer",
            "component": "houston",
            "release": "release-name",
            "app": "houston",
            "plane": "unified",
        }.items() <= houston_deployment["spec"]["template"]["metadata"]["labels"].items()

        c_by_name = get_containers_by_name(houston_deployment, include_init_containers=True)
        assert len(c_by_name) == 4
        houston_container, etc_ssl_certs_copier_container, wait_for_db_container, houston_bootstrapper_container = (
            c_by_name.values()
        )

        assert etc_ssl_certs_copier_container["securityContext"]["readOnlyRootFilesystem"]

        assert houston_bootstrapper_container["securityContext"]["readOnlyRootFilesystem"]
        assert houston_bootstrapper_container["image"].startswith("quay.io/astronomer/ap-db-bootstrapper:")
        assert houston_container["image"].startswith("quay.io/astronomer/ap-houston-api:")
        assert wait_for_db_container["image"].startswith("quay.io/astronomer/ap-houston-api:")

        assert houston_container["securityContext"]["readOnlyRootFilesystem"]
        houston_container_env = get_env_vars_dict(houston_container["env"])
        assert houston_container_env["DEPLOYMENTS__DATABASE__CONNECTION"]["secretKeyRef"]
        assert houston_container_env["COMMANDER_WAIT_ENABLED"] == "true"
        assert houston_container_env["REGISTRY_WAIT_ENABLED"] == "true"
        assert houston_container_env["DEPLOYMENTS__DATABASE__CONNECTION"] == {
            "secretKeyRef": {"key": "connection", "name": "release-name-houston-backend"}
        }

        assert wait_for_db_container["securityContext"]["readOnlyRootFilesystem"]
        wait_for_db_container_env = get_env_vars_dict(wait_for_db_container["env"])
        assert wait_for_db_container_env["COMMANDER_WAIT_ENABLED"] == "true"
        assert wait_for_db_container_env["REGISTRY_WAIT_ENABLED"] == "true"

    def test_houston_api_deployment_control_mode(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"

        c_by_name = get_containers_by_name(doc, include_init_containers=True)

        env_vars = get_env_vars_dict(c_by_name["houston"]["env"])
        assert env_vars["COMMANDER_WAIT_ENABLED"] == "false"
        assert env_vars["REGISTRY_WAIT_ENABLED"] == "false"

        env_vars = get_env_vars_dict(c_by_name["wait-for-db"]["env"])
        assert env_vars["COMMANDER_WAIT_ENABLED"] == "false"
        assert env_vars["REGISTRY_WAIT_ENABLED"] == "false"

    def test_houston_api_deployment_with_helm_set_database(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
            values={"astronomer": {"houston": {"config": {"deployments": {"database": {"connection": {"host": "1.1.1.1"}}}}}}},
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=True)
        houston_container_env = c_by_name["houston"]["env"]

        deployments_database_connection_env = next(
            (x for x in houston_container_env if x["name"] == "DEPLOYMENTS__DATABASE__CONNECTION"),
            None,
        )
        assert deployments_database_connection_env is None

    def test_houston_api_deployment_private_registry_with_secret_name_undefined(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
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

    def test_houston_api_deployment_private_registry_with_secret_name_defined(self, kube_version):
        secretName = "shhhhh"
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
            values={"global": {"privateRegistry": {"enabled": True, "secretName": secretName}}},
        )
        assert jmespath.search("spec.template.spec.imagePullSecrets[0].name", docs[0]) == secretName

    def test_houston_api_deployment_with_updates_url_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"updateRuntimeCheck": {"enabled": True}}}},
            show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = c_by_name["houston"]["env"]
        expected_runtime_env = {
            "name": "HOUSTON_SCRIPT_UPDATE_RUNTIME_SERVICE_URL",
            "value": "https://updates.astronomer.io/astronomer-runtime",
        }
        assert expected_runtime_env in houston_container_env

    def test_houston_api_deployment_with_updates_url_overrides(self, kube_version):
        CUSTOM_RUNTIME_URL = "https://test.me.io/astronomer-runtime"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "updateRuntimeCheck": {
                            "enabled": True,
                            "url": CUSTOM_RUNTIME_URL,
                        },
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = c_by_name["houston"]["env"]

        expected_runtime_env = {
            "name": "HOUSTON_SCRIPT_UPDATE_RUNTIME_SERVICE_URL",
            "value": CUSTOM_RUNTIME_URL,
        }
        assert expected_runtime_env in houston_container_env

    def test_houston_api_deployment_passing_in_base_houston_host_in_env(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = c_by_name["houston"]["env"]

        expected_env = {
            "name": "HOUSTON__HOST",
            "value": "release-name-houston",
        }
        assert expected_env in houston_container_env

    def test_houston_env_custom_release_name(self, kube_version):
        """Ensure all houston environment __HOST variables use the custom release name."""
        docs = render_chart(
            name="custom-name",
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
        )
        c_by_name = get_containers_by_name(docs[0])
        houston_env = get_env_vars_dict(c_by_name["houston"]["env"])
        assert all(v.startswith("custom-name") for k, v in houston_env.items() if k.endswith("__HOST"))

    def test_houston_configmap_with_runtimeReleasesConfig_enabled(self, kube_version):
        """Validate the houston configmap and its embedded data with RuntimeReleasesConfig defined
        ."""
        runtime_releases_json = {"runtimeVersions": {"12.1.1": {"metadata": {"airflowVersion": "2.2.5", "channel": "stable"}}}}
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"runtimeReleasesConfig": runtime_releases_json}}},
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
            ],
        )
        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["astro_runtime_releases.json"])
        assert prod == runtime_releases_json
        doc = docs[1]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        assert {
            "name": "houston-config-volume",
            "mountPath": "/houston/astro_runtime_releases.json",
            "subPath": "astro_runtime_releases.json",
        } in c_by_name["houston"]["volumeMounts"]

    def test_houston_configmap_with_airflow_and_runtime_configmap_name_enabled(self, kube_version):
        """Validate that houston configmap and its embedded data with runtime and airflow configmap name defined."""
        runtimeConfigmapName = "runtime-certfied-json"

        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "runtimeReleasesConfigMapName": runtimeConfigmapName,
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
            ],
        )
        doc = docs[0]
        assert "astro_runtime_releases.json" not in doc["data"]
        assert "airflow_releases.json" not in doc["data"]
        doc = docs[1]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        assert {
            "name": "runtimeversions",
            "mountPath": "/houston/astro_runtime_releases.json",
            "subPath": "astro_runtime_releases.json",
        } in c_by_name["houston"]["volumeMounts"]

        assert {"configMap": {"name": runtimeConfigmapName}, "name": "runtimeversions"} in doc["spec"]["template"]["spec"][
            "volumes"
        ]

    def test_houston_deployments_containers_with_custom_houston_secret_name(self, kube_version):
        """Test Upgrade Deployments Job Init Containers are disabled when custom houston secret name is passed."""

        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "upgradeDeployments": {"enabled": True},
                        "backendSecretName": "houstonbackend",
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
        )

        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert "initContainers" not in spec
        assert "default" == spec["serviceAccountName"]
        c_by_name = get_containers_by_name(docs[0], include_init_containers=True)
        env_vars = {x["name"]: x.get("value", x.get("valueFrom")) for x in c_by_name["houston"]["env"]}
        assert env_vars["DATABASE__CONNECTION"] == {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}}
        assert env_vars["DATABASE_URL"] == {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}}
        assert env_vars["DEPLOYMENTS__DATABASE__CONNECTION"] == {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}}

    def test_houston_deployments_containers_with_custom_secret_name(self, kube_version):
        """Test houston Deployments Init Containers disabled when custom houston secret name is passed."""

        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "upgradeDeployments": {"enabled": True},
                        "airflowBackendSecretName": "afwbackend",
                        "backendSecretName": "houstonbackend",
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/api/houston-deployment.yaml"],
        )

        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert "initContainers" not in spec
        assert "default" == spec["serviceAccountName"]
        c_by_name = get_containers_by_name(docs[0], include_init_containers=True)
        env_vars = {x["name"]: x.get("value", x.get("valueFrom")) for x in c_by_name["houston"]["env"]}
        assert env_vars["DATABASE__CONNECTION"] == {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}}
        assert env_vars["DATABASE_URL"] == {"secretKeyRef": {"name": "houstonbackend", "key": "connection"}}
        assert env_vars["DEPLOYMENTS__DATABASE__CONNECTION"] == {"secretKeyRef": {"name": "afwbackend", "key": "connection"}}
