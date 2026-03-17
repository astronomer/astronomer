import jmespath
import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonWorkerDeployment:
    def test_houston_worker_deployment_defaults(self, kube_version):
        """Test the default configuration of the Houston worker deployment."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        worker_deployment = docs[0]
        assert worker_deployment["kind"] == "Deployment"
        assert worker_deployment["spec"]["selector"]["matchLabels"] == {
            "tier": "astronomer",
            "component": "houston-worker",
            "release": "release-name",
        }

        # Ensure the first dict is contained within the larger labels dict
        assert {
            "tier": "astronomer",
            "component": "houston-worker",
            "release": "release-name",
            "app": "houston-worker",
            "plane": "unified",
        }.items() <= worker_deployment["spec"]["template"]["metadata"]["labels"].items()

        c_by_name = get_containers_by_name(worker_deployment, include_init_containers=True)
        assert len(c_by_name) == 4
        houston_container, _etc_ssl_certs_copier_container, _wait_for_db_container, _houston_bootstrapper_container = (
            c_by_name.values()
        )

        assert houston_container["securityContext"]["readOnlyRootFilesystem"]
        assert houston_container["image"].startswith("quay.io/astronomer/ap-houston-api:")
        houston_container_env = get_env_vars_dict(houston_container["env"])
        assert houston_container_env["APOLLO_SERVER_ID"]["fieldRef"]["fieldPath"] == "metadata.name"
        assert houston_container_env["GRPC_VERBOSITY"] == "INFO"
        assert houston_container_env["GRPC_TRACE"] == "all"

    def test_houston_worker_deployment_control_mode(self, kube_version):
        """Test houston worker deployment in control plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Deployment"

        c_by_name = get_containers_by_name(doc, include_init_containers=True)
        env_vars = get_env_vars_dict(c_by_name["houston"]["env"])
        assert env_vars["COMMANDER_WAIT_ENABLED"] == "false"
        assert env_vars["REGISTRY_WAIT_ENABLED"] == "false"

    def test_houston_worker_deployment_not_rendered_in_data_plane(self, kube_version):
        """Test that houston worker is not rendered when in data plane mode."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 0

    def test_houston_worker_deployment_dispatcher_disabled_by_default(self, kube_version):
        """Test that dispatcher is disabled by default."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = c_by_name["houston"]["env"]

        dispatcher_enabled_env = next(
            (x for x in houston_container_env if x["name"] == "DISPATCHER_ENABLED"),
            None,
        )
        assert dispatcher_enabled_env is not None
        assert dispatcher_enabled_env["value"] == "false"

    def test_houston_worker_deployment_dispatcher_enabled(self, kube_version):
        """Test that dispatcher environment variables are set when enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"worker": {"dispatcher": {"enabled": True}}}}},
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = get_env_vars_dict(c_by_name["houston"]["env"])

        assert houston_container_env["DISPATCHER_ENABLED"] == "true"

    def test_houston_worker_deployment_dispatcher_lease_ttl(self, kube_version):
        """Test dispatcher lease TTL configuration."""
        CUSTOM_TTL = 45
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "worker": {
                            "dispatcher": {
                                "enabled": True,
                                "lease": {"ttlSeconds": CUSTOM_TTL},
                            }
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = get_env_vars_dict(c_by_name["houston"]["env"])

        assert houston_container_env["DISPATCH_LEASE_TTL_SECONDS"] == str(CUSTOM_TTL)

    def test_houston_worker_deployment_dispatcher_batch_size(self, kube_version):
        """Test dispatcher batch size configuration."""
        CUSTOM_BATCH_SIZE = 100
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "worker": {
                            "dispatcher": {
                                "enabled": True,
                                "batch": {"size": CUSTOM_BATCH_SIZE},
                            }
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = get_env_vars_dict(c_by_name["houston"]["env"])

        assert houston_container_env["DISPATCH_BATCH_SIZE"] == str(CUSTOM_BATCH_SIZE)

    def test_houston_worker_deployment_dispatcher_inflight_limits(self, kube_version):
        """Test dispatcher inflight limits configuration."""
        CUSTOM_MAX_INFLIGHT = 75
        CUSTOM_MAX_INFLIGHT_PER_DP = 10
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "worker": {
                            "dispatcher": {
                                "enabled": True,
                                "inflight": {
                                    "max": CUSTOM_MAX_INFLIGHT,
                                    "maxPerDp": CUSTOM_MAX_INFLIGHT_PER_DP,
                                },
                            }
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = get_env_vars_dict(c_by_name["houston"]["env"])

        assert houston_container_env["DISPATCH_MAX_INFLIGHT"] == str(CUSTOM_MAX_INFLIGHT)
        assert houston_container_env["DISPATCH_MAX_INFLIGHT_PER_DP"] == str(CUSTOM_MAX_INFLIGHT_PER_DP)

    def test_houston_worker_deployment_dispatcher_poll_seconds(self, kube_version):
        """Test dispatcher poll interval configuration."""
        CUSTOM_POLL_SECONDS = 15
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "worker": {
                            "dispatcher": {
                                "enabled": True,
                                "poll": {"seconds": CUSTOM_POLL_SECONDS},
                            }
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = get_env_vars_dict(c_by_name["houston"]["env"])

        assert houston_container_env["DISPATCH_POLL_SECONDS"] == str(CUSTOM_POLL_SECONDS)

    def test_houston_worker_deployment_dispatcher_max_attempts(self, kube_version):
        """Test dispatcher max attempts configuration."""
        CUSTOM_ATTEMPTS_PER_LEASE = 8
        CUSTOM_ATTEMPTS_PER_FLIGHT = 40
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "worker": {
                            "dispatcher": {
                                "enabled": True,
                                "maxAttemptsPerLease": CUSTOM_ATTEMPTS_PER_LEASE,
                                "maxAttemptsPerFlight": CUSTOM_ATTEMPTS_PER_FLIGHT,
                            }
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = get_env_vars_dict(c_by_name["houston"]["env"])

        assert houston_container_env["DISPATCH_MAX_ATTEMPTS_PER_LEASE"] == str(CUSTOM_ATTEMPTS_PER_LEASE)
        assert houston_container_env["DISPATCH_MAX_ATTEMPTS_PER_FLIGHT"] == str(CUSTOM_ATTEMPTS_PER_FLIGHT)

    def test_houston_worker_deployment_dispatcher_retry_cooloff(self, kube_version):
        """Test dispatcher retry cooloff period configuration."""
        CUSTOM_COOLOFF_SECONDS = 120
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "worker": {
                            "dispatcher": {
                                "enabled": True,
                                "retryCooloffPeriodSeconds": CUSTOM_COOLOFF_SECONDS,
                            }
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = get_env_vars_dict(c_by_name["houston"]["env"])

        assert houston_container_env["DISPATCH_RETRY_COOLOFF_PERIOD"] == str(CUSTOM_COOLOFF_SECONDS)

    def test_houston_worker_deployment_dispatcher_rpc_timeouts(self, kube_version):
        """Test dispatcher RPC timeout configuration."""
        CUSTOM_INREGION_TIMEOUT = 8000
        CUSTOM_CROSSREGION_TIMEOUT = 15000
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "worker": {
                            "dispatcher": {
                                "enabled": True,
                                "rpc": {
                                    "inRegionTimeoutMs": CUSTOM_INREGION_TIMEOUT,
                                    "crossRegionTimeoutMs": CUSTOM_CROSSREGION_TIMEOUT,
                                },
                            }
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = get_env_vars_dict(c_by_name["houston"]["env"])

        assert houston_container_env["IN_REGION_STARTFLIGHT_RPC_TIMEOUT"] == str(CUSTOM_INREGION_TIMEOUT)
        assert houston_container_env["CROSS_REGION_STARTFLIGHT_RPC_TIMEOUT"] == str(CUSTOM_CROSSREGION_TIMEOUT)

    def test_houston_worker_deployment_dispatcher_circuit_breaker_defaults(self, kube_version):
        """Test dispatcher circuit breaker default configuration."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "worker": {
                            "dispatcher": {
                                "enabled": True,
                            }
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = get_env_vars_dict(c_by_name["houston"]["env"])

        assert houston_container_env["CB_FAILURE_THRESHOLD"] == "10"
        assert houston_container_env["CB_COOLOFF_SECONDS"] == "30"
        assert houston_container_env["CB_PROBE_MAX_INFLIGHT"] == "1"

    def test_houston_worker_deployment_dispatcher_circuit_breaker_custom(self, kube_version):
        """Test dispatcher circuit breaker custom configuration."""
        CUSTOM_FAILURE_THRESHOLD = 20
        CUSTOM_COOLOFF_SECONDS = 60
        CUSTOM_PROBE_MAX_INFLIGHT = 5
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "worker": {
                            "dispatcher": {
                                "enabled": True,
                                "circuitBreaker": {
                                    "failureThreshold": CUSTOM_FAILURE_THRESHOLD,
                                    "cooloffSeconds": CUSTOM_COOLOFF_SECONDS,
                                    "probeMaxInflight": CUSTOM_PROBE_MAX_INFLIGHT,
                                },
                            }
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = get_env_vars_dict(c_by_name["houston"]["env"])

        assert houston_container_env["CB_FAILURE_THRESHOLD"] == str(CUSTOM_FAILURE_THRESHOLD)
        assert houston_container_env["CB_COOLOFF_SECONDS"] == str(CUSTOM_COOLOFF_SECONDS)
        assert houston_container_env["CB_PROBE_MAX_INFLIGHT"] == str(CUSTOM_PROBE_MAX_INFLIGHT)

    def test_houston_worker_deployment_all_dispatcher_defaults(self, kube_version):
        """Test all dispatcher default values when enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "worker": {
                            "dispatcher": {
                                "enabled": True,
                            }
                        }
                    }
                }
            },
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        c_by_name = get_containers_by_name(doc, include_init_containers=False)
        houston_container_env = get_env_vars_dict(c_by_name["houston"]["env"])

        # Verify all dispatcher environment variables are present with correct default values
        assert houston_container_env["DISPATCHER_ENABLED"] == "true"
        assert houston_container_env["DISPATCH_LEASE_TTL_SECONDS"] == "30"
        assert houston_container_env["DISPATCH_BATCH_SIZE"] == "50"
        assert houston_container_env["DISPATCH_MAX_INFLIGHT"] == "50"
        assert houston_container_env["DISPATCH_MAX_INFLIGHT_PER_DP"] == "5"
        assert houston_container_env["DISPATCH_POLL_SECONDS"] == "10"
        assert houston_container_env["DISPATCH_MAX_ATTEMPTS_PER_LEASE"] == "5"
        assert houston_container_env["DISPATCH_MAX_ATTEMPTS_PER_FLIGHT"] == "25"
        assert houston_container_env["DISPATCH_RETRY_COOLOFF_PERIOD"] == "60"
        assert houston_container_env["IN_REGION_STARTFLIGHT_RPC_TIMEOUT"] == "5000"
        assert houston_container_env["CROSS_REGION_STARTFLIGHT_RPC_TIMEOUT"] == "12000"
        assert houston_container_env["CB_FAILURE_THRESHOLD"] == "10"
        assert houston_container_env["CB_COOLOFF_SECONDS"] == "30"
        assert houston_container_env["CB_PROBE_MAX_INFLIGHT"] == "1"

    def test_houston_worker_deployment_private_registry_with_secret_name_defined(self, kube_version):
        """Test houston worker deployment private registry configuration."""
        secretName = "my-docker-secret"
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
            values={"global": {"privateRegistry": {"enabled": True, "secretName": secretName}}},
        )
        assert jmespath.search("spec.template.spec.imagePullSecrets[0].name", docs[0]) == secretName

    def test_houston_worker_deployment_with_custom_replicas(self, kube_version):
        """Test houston worker deployment with custom replica count."""
        CUSTOM_REPLICAS = 5
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {"worker": {"replicas": CUSTOM_REPLICAS}}}},
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["spec"]["replicas"] == CUSTOM_REPLICAS
