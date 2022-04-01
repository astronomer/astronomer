from tests.unit_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions, get_containers_by_name


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestNatsStatefulSet:
    def test_nats_statefulset_defaults(self, kube_version):
        """Test that nats statefulset is good with defaults."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/nats/templates/statefulset.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-nats"
        assert c_by_name["metrics"]["image"].startswith(
            "quay.io/astronomer/ap-nats-exporter:"
        )
        assert c_by_name["nats"]["image"].startswith(
            "quay.io/astronomer/ap-nats-server:"
        )
        assert c_by_name["nats"]["livenessProbe"] == {
            "httpGet": {"path": "/", "port": 8222},
            "initialDelaySeconds": 10,
            "timeoutSeconds": 5,
        }
        assert c_by_name["nats"]["readinessProbe"] == {
            "httpGet": {"path": "/", "port": 8222},
            "initialDelaySeconds": 10,
            "timeoutSeconds": 5,
        }

        assert doc["spec"]["template"]["spec"]["nodeSelector"] == {}
        assert doc["spec"]["template"]["spec"]["affinity"] == {}
        assert doc["spec"]["template"]["spec"]["tolerations"] == []

    def test_nats_statefulset_with_metrics_and_resources(self, kube_version):
        """Test that nats statefulset renders good metrics exporter."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/nats/templates/statefulset.yaml"],
            values={
                "nats": {
                    "exporter": {
                        "enabled": True,
                        "resources": {"requests": {"cpu": "234m"}},
                    },
                    "nats": {"resources": {"requests": {"cpu": "123m"}}},
                },
            },
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert len(c_by_name) == 2
        assert c_by_name["nats"]["resources"]["requests"]["cpu"] == "123m"
        assert c_by_name["metrics"]["resources"]["requests"]["cpu"] == "234m"

    def test_nats_statefulset_with_affinity_and_tolerations(self, kube_version):
        """Test that nats statefulset renders proper nodeSelector, affinity, and tolerations"""
        values = {
            "nats": {
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
            show_only=["charts/nats/templates/statefulset.yaml"],
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
        assert spec["tolerations"] == values["nats"]["tolerations"]

    def test_nats_statefulset_with_global_affinity_and_tolerations(self, kube_version):
        """Test that nats statefulset renders proper nodeSelector, affinity, and tolerations with global config"""
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
            show_only=["charts/nats/templates/statefulset.yaml"],
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
