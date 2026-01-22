import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPGBouncerDeployment:
    def test_pgbouncer_deployment_defaults(self, kube_version):
        """Test pgbouncer deployment defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"pgbouncer": {"enabled": True}}},
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )

        assert len(docs) == 1
        deployment = docs[0]

        assert deployment["kind"] == "Deployment"
        assert deployment["metadata"]["name"] == "release-name-pgbouncer"

        c_by_name = get_containers_by_name(deployment)
        assert len(c_by_name) == 1
        assert c_by_name["pgbouncer"]["securityContext"] == {"readOnlyRootFilesystem": True, "runAsNonRoot": True}
        assert c_by_name["pgbouncer"]["resources"] == {
            "limits": {"cpu": "250m", "memory": "256Mi"},
            "requests": {"cpu": "250m", "memory": "256Mi"},
        }
        assert c_by_name["pgbouncer"]["env"] is None

    def test_pgbouncer_deployment_custom_configurations(self, kube_version):
        """Test pgbouncer deployment with custom configurations."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"pgbouncer": {"enabled": True, "extraEnv": {"red": "blue"}}},
                "pgbouncer": {
                    "env": {"foo_key": "foo_value", "bar_key": "bar_value"},
                    "securityContext": {
                        "snoopy": "dog",
                        "woodstock": "bird",
                    },
                },
            },
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert len(c_by_name) == 1
        assert c_by_name["pgbouncer"]["securityContext"] == {
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
            "snoopy": "dog",
            "woodstock": "bird",
        }

        c_env = get_env_vars_dict(c_by_name["pgbouncer"]["env"])
        assert c_env["red"] == "blue"
        assert c_env["bar_key"] == "bar_value"
        assert c_env["foo_key"] == "foo_value"

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
        """Test that the pgbouncer deployment mounts the configured secret and tmp-workspace volumes."""
        secret_name = "astronomer-pgbouncer-config"
        doc = render_chart(
            kube_version=kube_version,
            values={"global": {"pgbouncer": {"enabled": True, "secretName": secret_name}}},
            show_only=["charts/pgbouncer/templates/pgbouncer-deployment.yaml"],
        )[0]

        pod_spec = doc["spec"]["template"]["spec"]

        # Check pgbouncer-config secret volume
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

        # Check tmp-workspace emptyDir volume
        assert {"name": "tmp-workspace", "emptyDir": {}} in pod_spec["volumes"]

        c_by_name = get_containers_by_name(doc)

        # Check pgbouncer-config volume mount
        assert {
            "name": "pgbouncer-config",
            "readOnly": True,
            "mountPath": "/etc/pgbouncer",
        } in c_by_name["pgbouncer"]["volumeMounts"]

        # Check tmp-workspace volume mount
        assert {
            "name": "tmp-workspace",
            "mountPath": "/tmp",
        } in c_by_name["pgbouncer"]["volumeMounts"]

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
        """Test that pgbouncer network policy is not created when disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"pgbouncer": {"enabled": True}},
                "pgbouncer": {"networkPolicies": {"enabled": False}},
            },
            show_only=["charts/pgbouncer/templates/pgbouncer-networkpolicy.yaml"],
        )

        assert len(docs) == 0
