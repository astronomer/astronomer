from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions


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
        c_by_name = {
            c["name"]: c for c in doc["spec"]["template"]["spec"]["containers"]
        }
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-stan"
        assert c_by_name["metrics"]["image"].startswith(
            "quay.io/astronomer/ap-nats-exporter:"
        )
        assert c_by_name["stan"]["image"].startswith(
            "quay.io/astronomer/ap-nats-streaming:"
        )
        assert c_by_name["stan"]["livenessProbe"] == {
            "httpGet": {"path": "/streaming/serverz", "port": "monitor"},
            "initialDelaySeconds": 10,
            "timeoutSeconds": 5,
        }
        assert c_by_name["stan"]["readinessProbe"] == {
            "httpGet": {"path": "/streaming/serverz", "port": "monitor"},
            "initialDelaySeconds": 10,
            "timeoutSeconds": 5,
        }

        assert doc["spec"]["template"]["spec"]["nodeSelector"] == {}
        assert doc["spec"]["template"]["spec"]["affinity"] == {}
        assert doc["spec"]["template"]["spec"]["tolerations"] == []

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
        containers = docs[0]["spec"]["template"]["spec"]["containers"]
        assert len(containers) == 2
        c_by_name = {c["name"]: c for c in containers}
        assert c_by_name["stan"]["resources"]["requests"]["cpu"] == "123m"
        assert c_by_name["metrics"]["resources"]["requests"]["cpu"] == "234m"

    def test_stan_statefulset_with_affinity_and_tolerations(self, kube_version):
        """Test that stan statefulset renders proper nodeSelector, affinity, and tolerations"""
        values = {
            "stan": {
                "nodeSelector": {"role": "astro"},
                "affinity": {
                    "nodeAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": {
                            "nodeSelectorTerms": [
                                {
                                    "matchExpressions": [
                                        {
                                            "key": "astronomer.io/multi-tenant",
                                            "operator": "In",
                                            "values": ["false"],
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                },
                "tolerations": [
                    {
                        "effect": "NoSchedule",
                        "key": "astronomer",
                        "operator": "Exists",
                    }
                ],
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
        assert spec["nodeSelector"]["role"] == "astro"
        assert spec["affinity"] != {}
        assert (
            len(
                spec["affinity"]["nodeAffinity"][
                    "requiredDuringSchedulingIgnoredDuringExecution"
                ]["nodeSelectorTerms"]
            )
            == 1
        )
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["stan"]["tolerations"]

    def test_stan_statefulset_with_global_affinity_and_tolerations(self, kube_version):
        """Test that stan statefulset renders proper nodeSelector, affinity, and tolerations with global config"""
        values = {
            "global": {
                "platformNodePool": {
                    "nodeSelector": {"role": "astro"},
                    "affinity": {
                        "nodeAffinity": {
                            "requiredDuringSchedulingIgnoredDuringExecution": {
                                "nodeSelectorTerms": [
                                    {
                                        "matchExpressions": [
                                            {
                                                "key": "astronomer.io/multi-tenant",
                                                "operator": "In",
                                                "values": ["false"],
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    },
                    "tolerations": [
                        {
                            "effect": "NoSchedule",
                            "key": "astronomer",
                            "operator": "Exists",
                        }
                    ],
                },
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
        assert (
            len(
                spec["affinity"]["nodeAffinity"][
                    "requiredDuringSchedulingIgnoredDuringExecution"
                ]["nodeSelectorTerms"]
            )
            == 1
        )
        assert len(spec["tolerations"]) > 0
        assert (
            spec["tolerations"] == values["global"]["platformNodePool"]["tolerations"]
        )

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
        c_by_name = {
            c["name"]: c
            for c in doc["spec"]["template"]["spec"]["containers"]
            + doc["spec"]["template"]["spec"]["initContainers"]
        }

        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"

        assert (
            c_by_name["stan"]["image"]
            == "example.com/custom/image/the-stan-image:the-custom-stan-tag"
        )
        assert c_by_name["stan"]["imagePullPolicy"] == "Always"
        assert (
            c_by_name["wait-for-nats-server"]["image"]
            == "example.com/custom/image/the-init-image:the-custom-init-tag"
        )
        assert c_by_name["stan"]["imagePullPolicy"] == "Always"

    def test_stan_statefulset_with_private_registry(self, kube_version):
        """Test that stan statefulset properly uses the private registry images."""
        private_repo = "example.com/the-private-registry-repository"
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/stan/templates/statefulset.yaml"],
            values={
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        "repository": private_repo,
                    }
                }
            },
        )

        assert len(docs) == 1
        doc = docs[0]

        c_by_name = {
            c["name"]: c
            for c in doc["spec"]["template"]["spec"]["containers"]
            + doc["spec"]["template"]["spec"]["initContainers"]
        }

        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"

        for name, container in c_by_name.items():
            assert container["image"].startswith(
                private_repo
            ), f"The container '{name}' does not use the privateRegistry repo '{private_repo}': {container}"
