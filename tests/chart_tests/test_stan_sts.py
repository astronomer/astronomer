import re

import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestStanStatefulSet:
    def test_stan_statefulset_defaults(self, kube_version):
        """Test that stan statefulset is good with defaults."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/stan/templates/statefulset.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-stan"
        assert "persistentVolumeClaimRetentionPolicy" not in doc["spec"]

        c_by_name = get_containers_by_name(doc, include_init_containers=True)
        assert c_by_name["metrics"]["image"].startswith("quay.io/astronomer/ap-nats-exporter:")
        assert c_by_name["stan"]["image"].startswith("quay.io/astronomer/ap-nats-streaming:")

        stan_lp = c_by_name["stan"]["livenessProbe"]
        assert stan_lp["httpGet"] == {"path": "/streaming/serverz", "port": "monitor"}
        assert stan_lp["initialDelaySeconds"] == 10
        assert stan_lp["timeoutSeconds"] == 5

        stan_rp = c_by_name["stan"]["readinessProbe"]
        assert stan_rp["httpGet"] == {"path": "/streaming/serverz", "port": "monitor"}
        assert stan_rp["initialDelaySeconds"] == 10
        assert not stan_rp.get("periodSeconds")
        assert not stan_rp.get("failureThreshold")
        assert stan_rp["timeoutSeconds"] == 5

        assert all(c["securityContext"] == {"readOnlyRootFilesystem": True, "runAsNonRoot": True} for c in c_by_name.values())
        sts_spec = doc["spec"]["template"]["spec"]
        assert sts_spec["nodeSelector"] == {}
        assert sts_spec["affinity"] == {}
        assert sts_spec["tolerations"] == []

    def test_stan_statefulset_with_security_context_overrides(self, kube_version):
        """Test that stan statefulset renders good metrics exporter."""

        securityContextResponse = {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
        }
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/stan/templates/statefulset.yaml"],
            values={
                "stan": {
                    "securityContext": {
                        "runAsNonRoot": True,
                        "allowPrivilegeEscalation": False,
                    },
                },
            },
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0], include_init_containers=True)
        assert len(c_by_name) == 3
        assert all(c["securityContext"] == securityContextResponse for c in c_by_name.values())

    def test_stan_statefulset_with_metrics_and_resources(self, kube_version):
        """Test that stan statefulset renders good metrics exporter."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/stan/templates/statefulset.yaml"],
            values={
                "stan": {
                    "exporter": {
                        "enabled": True,
                        "resources": {"requests": {"cpu": "234m"}},
                    },
                    "stan": {"resources": {"requests": {"cpu": "123m"}}},
                },
            },
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert len(c_by_name) == 2
        assert c_by_name["stan"]["resources"]["requests"]["cpu"] == "123m"
        assert c_by_name["metrics"]["resources"]["requests"]["cpu"] == "234m"

    def test_stan_statefulset_with_global_affinity_and_tolerations(self, kube_version, global_platform_node_pool_config):
        """Test that stan statefulset renders proper nodeSelector, affinity,
        and tolerations with global config."""
        values = {
            "global": {
                "platformNodePool": global_platform_node_pool_config,
            }
        }
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/stan/templates/statefulset.yaml"],
            values=values,
        )

        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert spec["nodeSelector"] != {}
        assert spec["nodeSelector"]["role"] == "astro"
        assert spec["affinity"] != {}
        assert len(spec["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["global"]["platformNodePool"]["tolerations"]

    def test_stan_statefulset_with_affinity_and_tolerations(self, kube_version, global_platform_node_pool_config):
        """Test that stan statefulset renders proper nodeSelector, affinity,
        and tolerations."""
        global_platform_node_pool_config["nodeSelector"] = {"role": "astrostan"}
        values = {
            "stan": {
                "nodeSelector": global_platform_node_pool_config["nodeSelector"],
                "affinity": global_platform_node_pool_config["affinity"],
                "tolerations": global_platform_node_pool_config["tolerations"],
            },
        }
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/stan/templates/statefulset.yaml"],
            values=values,
        )

        assert len(docs) == 1
        spec = docs[0]["spec"]["template"]["spec"]
        assert spec["nodeSelector"] != {}
        assert spec["nodeSelector"]["role"] == "astrostan"
        assert spec["affinity"] != {}
        assert len(spec["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["stan"]["tolerations"]

    def test_stan_statefulset_with_custom_images(self, kube_version):
        """Test we can customize the stan images."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/stan/templates/statefulset.yaml"],
            values={
                "stan": {
                    "images": {
                        "init": {
                            "repository": "example.com/custom/image/the-init-image",
                            "tag": "the-custom-init-tag",
                            "pullPolicy": "Always",
                        },
                        "stan": {
                            "repository": "example.com/custom/image/the-stan-image",
                            "tag": "the-custom-stan-tag",
                            "pullPolicy": "Always",
                        },
                    },
                },
            },
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=True)

        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"

        assert c_by_name["stan"]["image"] == "example.com/custom/image/the-stan-image:the-custom-stan-tag"
        assert c_by_name["stan"]["imagePullPolicy"] == "Always"
        assert c_by_name["wait-for-nats-server"]["image"] == "example.com/custom/image/the-init-image:the-custom-init-tag"
        assert c_by_name["stan"]["imagePullPolicy"] == "Always"

    def test_stan_statefulset_with_private_registry(self, kube_version):
        """Test that stan statefulset properly uses the private registry
        images."""
        private_registry = "private-registry.example.com"
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/stan/templates/statefulset.yaml"],
            values={
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        "repository": private_registry,
                    }
                }
            },
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc, include_init_containers=True)

        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"

        for name, container in c_by_name.items():
            assert container["image"].startswith(private_registry), (
                f"Container named '{name}' does not use registry '{private_registry}': {container}"
            )

    def test_stan_configmap_with_logging_defaults(self, kube_version):
        """Test that stan configmap with logging defaults."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/stan/templates/configmap.yaml"],
            values={},
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        config = doc["data"]["stan.conf"]
        sd_match = re.search(r"sd:\s+(.*?)\n", config)
        assert sd_match[1] == "true"

    def test_stan_configmap_with_logging_overrides(self, kube_version):
        """Test that stan configmap with logging defaults."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/stan/templates/configmap.yaml"],
            values={
                "stan": {"stan": {"logging": {"trace": "true"}}},
            },
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        config = doc["data"]["stan.conf"]
        sd_match = re.search(r"sd:\s+(.*?)\n", config)
        sv_match = re.search(r"sv:\s+(.*?)\n", config)
        assert sd_match[1] == "true"
        assert sv_match[1] == "true"

    def test_stan_persistentVolumeClaimRetentionPolicy(self, kube_version):
        test_persistentVolumeClaimRetentionPolicy = {
            "whenDeleted": "Delete",
            "whenScaled": "Retain",
        }
        doc = render_chart(
            kube_version=kube_version,
            values={
                "stan": {
                    "persistence": {
                        "persistentVolumeClaimRetentionPolicy": test_persistentVolumeClaimRetentionPolicy,
                    },
                },
            },
            show_only=[
                "charts/stan/templates/statefulset.yaml",
            ],
        )

        assert len(doc) == 1

        assert "persistentVolumeClaimRetentionPolicy" in doc[0]["spec"]
        assert test_persistentVolumeClaimRetentionPolicy == doc[0]["spec"]["persistentVolumeClaimRetentionPolicy"]
