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

    def test_houston_worker_deployment_dispatcher_defaults(self, kube_version):
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

    def test_houston_worker_deployment_dispatcher_custom_values(self, kube_version):
        """Test dispatcher with custom values for all configurable parameters."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "astronomer": {
                    "houston": {
                        "worker": {
                            "dispatcher": {
                                "enabled": True,
                                "lease": {"ttlSeconds": 45},
                                "batch": {"size": 100},
                                "inflight": {
                                    "max": 75,
                                    "maxPerDp": 10,
                                },
                                "poll": {"seconds": 15},
                                "maxAttemptsPerLease": 8,
                                "maxAttemptsPerFlight": 40,
                                "retryCooloffPeriodSeconds": 120,
                                "rpc": {
                                    "inRegionTimeoutMs": 8000,
                                    "crossRegionTimeoutMs": 15000,
                                },
                                "circuitBreaker": {
                                    "failureThreshold": 20,
                                    "cooloffSeconds": 60,
                                    "probeMaxInflight": 5,
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

        # Verify all dispatcher custom values
        assert houston_container_env["DISPATCHER_ENABLED"] == "true"
        assert houston_container_env["DISPATCH_LEASE_TTL_SECONDS"] == "45"
        assert houston_container_env["DISPATCH_BATCH_SIZE"] == "100"
        assert houston_container_env["DISPATCH_MAX_INFLIGHT"] == "75"
        assert houston_container_env["DISPATCH_MAX_INFLIGHT_PER_DP"] == "10"
        assert houston_container_env["DISPATCH_POLL_SECONDS"] == "15"
        assert houston_container_env["DISPATCH_MAX_ATTEMPTS_PER_LEASE"] == "8"
        assert houston_container_env["DISPATCH_MAX_ATTEMPTS_PER_FLIGHT"] == "40"
        assert houston_container_env["DISPATCH_RETRY_COOLOFF_PERIOD"] == "120"
        assert houston_container_env["IN_REGION_STARTFLIGHT_RPC_TIMEOUT"] == "8000"
        assert houston_container_env["CROSS_REGION_STARTFLIGHT_RPC_TIMEOUT"] == "15000"
        assert houston_container_env["CB_FAILURE_THRESHOLD"] == "20"
        assert houston_container_env["CB_COOLOFF_SECONDS"] == "60"
        assert houston_container_env["CB_PROBE_MAX_INFLIGHT"] == "5"

    def test_houston_worker_deployment_private_registry_with_secret_name_defined(self, kube_version):
        """Test houston worker deployment private registry configuration."""
        secretName = "my-docker-secret"
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
            values={"global": {"privateRegistry": {"enabled": True, "secretName": secretName}}},
        )
        image_pull_secrets = docs[0]["spec"]["template"]["spec"]["imagePullSecrets"]
        assert image_pull_secrets[0]["name"] == secretName

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

    def test_houston_worker_deployment_has_backend_secret_checksum_annotation(self, kube_version):
        """Test that the worker pod template includes a checksum annotation for the houston backend secret.

        This ensures the worker deployment rolling-updates when the backend secret template
        changes (e.g. on helm upgrade), mirroring the same annotation already present on the
        API deployment.
        """
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml"],
        )

        assert len(docs) == 1
        annotations = docs[0]["spec"]["template"]["metadata"]["annotations"]
        assert "checksum/houston-backend-secret" in annotations
        # Must be a non-empty sha256 hex string (64 chars)
        checksum = annotations["checksum/houston-backend-secret"]
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_houston_worker_backend_secret_checksum_matches_api_deployment(self, kube_version):
        """Test that the worker and API deployments share the same backend secret checksum.

        Both deployments reference the same secret template, so their checksums must be identical.
        A mismatch would indicate that the worker and API are not restarted consistently.
        A deterministic backendConnection is supplied so randAlphaNum is not called (each
        include of the backend-secret template would otherwise re-evaluate randAlphaNum,
        producing different random values per include call).
        """
        deterministic_values = {
            "astronomer": {
                "houston": {
                    "backendSecretConnection": True,
                    "backendConnection": {
                        "user": "houston",
                        "pass": "s3cr3t",
                        "host": "pg.example.com",
                        "port": 5432,
                        "db": "houston",
                    },
                }
            }
        }
        docs = render_chart(
            kube_version=kube_version,
            values=deterministic_values,
            show_only=[
                "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
            ],
        )

        by_name = {d["metadata"]["name"]: d for d in docs}
        worker = by_name["release-name-houston-worker"]
        api = by_name["release-name-houston"]

        worker_checksum = worker["spec"]["template"]["metadata"]["annotations"]["checksum/houston-backend-secret"]
        api_checksum = api["spec"]["template"]["metadata"]["annotations"]["checksum/houston-backend-secret"]

        assert worker_checksum == api_checksum
