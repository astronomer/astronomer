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
        assert not doc["spec"]["template"]["spec"].get("env")

    def test_custom_environment(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "pgbouncer": {
                        "enabled": True,
                    }
                },
                "pgbouncer": {"env": {"foo_key": "foo_value", "bar_key": "bar_value"}},
            },
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )[0]

        c_env = doc["spec"]["template"]["spec"]["containers"][0]["env"]
        assert {"name": "bar_key", "value": "bar_value"} in c_env
        assert {"name": "foo_key", "value": "foo_value"} in c_env

    def test_custom_labels(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "pgbouncer": {
                        "enabled": True,
                        "extraLabels": {"test_label": "test_label1"},
                    }
                },
            },
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )[0]

        labels = doc["spec"]["template"]["metadata"]["labels"]
        assert labels.get("test_label") == "test_label1"

    def test_pgbouncer_deployment_with_private_registry(self, kube_version):
        """Test that pgbouncer deployment properly uses the private registry
        images."""
        private_registry = "private-registry.example.com"
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
            values={
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        "repository": private_registry,
                    },
                    "pgbouncer": {"enabled": True},
                }
            },
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=True)

        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"

        for name, container in c_by_name.items():
            assert container["image"].startswith(private_registry), (
                f"Container named '{name}' does not use registry '{private_registry}': {container}"
            )

    def test_pgbouncer_deployment_mounts_config_secret(self, kube_version):
        """Test that the pgbouncer deployment mounts the configured secret to /etc/pgbouncer."""
        secret_name = "astronomer-pgbouncer-config"
        doc = render_chart(
            kube_version=kube_version,
            values={"global": {"pgbouncer": {"enabled": True, "secretName": secret_name}}},
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )[0]

        pod_spec = doc["spec"]["template"]["spec"]
        assert {
            "name": "pgbouncer-config",
            "secret": {
                "secretName": secret_name,
                "items": [
                    {"key": "pgbouncer.ini", "path": "pgbouncer.ini"},
                    {"key": "users.txt", "path": "users.txt"},
                ],
            },
        } in pod_spec["volumes"]

        c_by_name = get_containers_by_name(doc)
        assert {
            "name": "pgbouncer-config",
            "readOnly": True,
            "mountPath": "/etc/pgbouncer",
        } in c_by_name["pgbouncer"]["volumeMounts"]

    def test_pgbouncer_deployment_not_created_when_disabled(self, kube_version):
        """Test that pgbouncer deployment is not created when pgbouncer is disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"pgbouncer": {"enabled": False}}},
        )

        # Verify that no pgbouncer deployment exists in the rendered templates
        pgbouncer_deployments = [
            doc for doc in docs if doc["kind"] == "Deployment" and doc["metadata"]["name"] == "release-name-pgbouncer"
        ]
        assert len(pgbouncer_deployments) == 0

    def test_pgbouncer_deployment_without_secret_name(self, kube_version):
        """Test that pgbouncer deployment does not mount pgbouncer-config volumes when secretName is explicitly empty."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"pgbouncer": {"enabled": True, "secretName": ""}}},
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        pod_spec = doc["spec"]["template"]["spec"]

        # Check that pgbouncer-config volume is not present
        volume_names = [vol.get("name") for vol in pod_spec.get("volumes", [])]
        assert "pgbouncer-config" not in volume_names

        c_by_name = get_containers_by_name(doc)

        # Check that pgbouncer-config volume mount is not present
        volume_mount_names = [vm.get("name") for vm in c_by_name["pgbouncer"].get("volumeMounts", [])]
        assert "pgbouncer-config" not in volume_mount_names

    def test_pgbouncer_deployment_custom_probes(self, kube_version):
        """Test pgbouncer deployment with custom liveness and readiness probes."""
        custom_liveness_probe = {
            "httpGet": {"path": "/health", "port": 8080},
            "initialDelaySeconds": 30,
            "periodSeconds": 20,
        }
        custom_readiness_probe = {
            "httpGet": {"path": "/ready", "port": 8080},
            "initialDelaySeconds": 15,
            "periodSeconds": 10,
        }

        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"pgbouncer": {"enabled": True}},
                "pgbouncer": {
                    "livenessProbe": custom_liveness_probe,
                    "readinessProbe": custom_readiness_probe,
                },
            },
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert len(c_by_name) == 1

        assert c_by_name["pgbouncer"]["livenessProbe"] == custom_liveness_probe
        assert c_by_name["pgbouncer"]["readinessProbe"] == custom_readiness_probe

    def test_pgbouncer_deployment_default_probes(self, kube_version):
        """Test pgbouncer deployment uses default tcpSocket probes when not customized."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"pgbouncer": {"enabled": True}}},
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert len(c_by_name) == 1

        # Default probes should be tcpSocket on port 6543
        assert c_by_name["pgbouncer"]["livenessProbe"] == {"tcpSocket": {"port": 6543}}
        assert c_by_name["pgbouncer"]["readinessProbe"] == {"tcpSocket": {"port": 6543}}


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPGBouncerNetworkPolicy:
    def test_pgbouncer_networkpolicy_enabled(self, kube_version):
        """Test that pgbouncer network policy is created when enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"pgbouncer": {"enabled": True}},
                "pgbouncer": {"networkPolicies": {"enabled": True}},
            },
            show_only=["charts/pgbouncer/templates/pgbouncer-networkpolicy.yaml"],
        )

        assert len(docs) == 1
        policy = docs[0]

        assert policy["kind"] == "NetworkPolicy"
        assert policy["apiVersion"] == "networking.k8s.io/v1"
        assert policy["metadata"]["name"] == "release-name-pgbouncer-policy"

        # Check podSelector
        assert policy["spec"]["podSelector"]["matchLabels"]["app"] == "pgbouncer"
        assert policy["spec"]["podSelector"]["matchLabels"]["release"] == "release-name"

        # Check ingress rules
        assert len(policy["spec"]["ingress"]) == 1
        ingress = policy["spec"]["ingress"][0]

        # Check port
        assert len(ingress["ports"]) == 1
        assert ingress["ports"][0]["port"] == 6543

        # Check from rules - should allow astronomer and monitoring tiers
        assert len(ingress["from"]) == 2

        # Check for astronomer tier
        astronomer_peer = {
            "podSelector": {
                "matchLabels": {
                    "release": "release-name",
                    "tier": "astronomer",
                }
            }
        }
        assert astronomer_peer in ingress["from"]

        # Check for monitoring tier
        monitoring_peer = {
            "podSelector": {
                "matchLabels": {
                    "release": "release-name",
                    "tier": "monitoring",
                }
            }
        }
        assert monitoring_peer in ingress["from"]

    def test_pgbouncer_networkpolicy_disabled(self, kube_version):
        """Test that pgbouncer network policy is not created when networkPolicies is disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"pgbouncer": {"enabled": True}},
                "pgbouncer": {"networkPolicies": {"enabled": False}},
            },
            show_only=["charts/pgbouncer/templates/pgbouncer-networkpolicy.yaml"],
        )

        assert len(docs) == 0

    def test_pgbouncer_networkpolicy_not_created_when_pgbouncer_disabled(self, kube_version):
        """Test that pgbouncer network policy is not created when pgbouncer is globally disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"pgbouncer": {"enabled": False}},
                "pgbouncer": {"networkPolicies": {"enabled": True}},
            },
        )

        # Verify that no pgbouncer network policy exists in the rendered templates
        pgbouncer_policies = [
            doc for doc in docs if doc["kind"] == "NetworkPolicy" and doc["metadata"]["name"] == "release-name-pgbouncer-policy"
        ]
        assert len(pgbouncer_policies) == 0
