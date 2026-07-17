import pytest
import yaml
from deepmerge import always_merger

from tests import supported_k8s_versions
from tests.utils import (
    find_all_pod_manager_templates,
    get_all_features,
    get_containers_by_name,
    pod_managers,
)
from tests.utils.chart import render_chart

show_only = [
    "charts/alertmanager/templates/alertmanager-statefulset.yaml",
    "charts/astronomer/templates/registry/registry-statefulset.yaml",
    "charts/elasticsearch/templates/client/es-client-deployment.yaml",
    "charts/elasticsearch/templates/data/es-data-statefulset.yaml",
    "charts/elasticsearch/templates/master/es-master-statefulset.yaml",
    "charts/nats/templates/statefulset.yaml",
]

airflow_components_list = [
    "apiServer",
    "flower",
    "webserver",
    "scheduler",
    "workers",
    "redis",
    "triggerer",
    "migrateDatabaseJob",
    "cleanup",
    "dagProcessor",
]


non_airflow_components_list = [
    "statsd",
    "pgbouncer",
]


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestOpenshift:
    def test_openshift_flag_defaults_with_enabled_and_validate_podsecuritycontext(self, kube_version):
        "Validate podSecurityContext is not set when openshiftEnabled is True"
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"openshift": {"enabled": True}},
            },
            show_only=show_only,
        )

        assert len(docs) == 6
        for doc in docs:
            assert "securityContext" in doc["spec"]["template"]["spec"]

    def test_openshift_flag_defaults_with_enabled_and_validate_houston_configmap(self, kube_version):
        "Validate houston config when openshiftEnabled is Enabled"
        docs = render_chart(
            values={
                "global": {"openshift": {"enabled": True}},
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])

        airflowConfig = prod["deployments"]["helm"]["airflow"]

        for component in airflow_components_list:
            assert {"runAsNonRoot": True} == airflowConfig[component]["securityContexts"]["pod"]

        for component in non_airflow_components_list:
            assert {"runAsNonRoot": True} == airflowConfig[component]["securityContexts"]["pod"]

        gitSyncConfig = airflowConfig["dags"]["gitSync"]
        assert {"runAsNonRoot": True} == gitSyncConfig["securityContexts"]["container"]

    def test_openshift_flag_defaults_with_enabled_and_validate_houston_configmap_gitsyncrelay(self, kube_version):
        """Validate gitSyncRelay securityContext in houston configmap when openshift is enabled."""
        docs = render_chart(
            values={
                "global": {"openshift": {"enabled": True}},
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])

        gitSyncRelayConfig = prod["deployments"]["helm"]["gitSyncRelay"]

        assert gitSyncRelayConfig["securityContext"] is None
        assert gitSyncRelayConfig["gitDaemon"]["securityContext"] == {
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
        }
        assert gitSyncRelayConfig["gitSync"]["securityContext"] == {
            "readOnlyRootFilesystem": True,
            "runAsNonRoot": True,
        }

    def test_openshift_disabled_houston_configmap_gitsyncrelay_no_security_overrides(self, kube_version):
        """Validate gitSyncRelay has no securityContext overrides when openshift is disabled."""
        docs = render_chart(
            values={
                "global": {"openshift": {"enabled": False}},
            },
            show_only=["charts/astronomer/templates/houston/houston-configmap.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])

        gitSyncRelayConfig = prod["deployments"]["helm"]["gitSyncRelay"]

        assert "securityContext" not in gitSyncRelayConfig
        assert "gitDaemon" not in gitSyncRelayConfig
        assert "gitSync" not in gitSyncRelayConfig

    def test_openshift_enabled_logging_sidecar_securitycontext_omits_runasuser(self, kube_version):
        """On OpenShift the logging-sidecar securityContext must omit runAsUser (the SCC assigns the
        UID), while keeping the enforced readOnlyRootFilesystem and the operator's other fields."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"openshift": {"enabled": True}},
                "astronomer": {
                    "houston": {
                        "logging": {
                            "loggingSidecar": {
                                "enabled": True,
                                "cloudwatch": {"enabled": True},
                                "securityContext": {"runAsUser": 1234},
                            },
                        },
                    },
                },
            },
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
            ],
        )

        assert len(docs) == 2
        for doc in docs:
            sc = get_containers_by_name(doc)["vector"]["securityContext"]
            assert "runAsUser" not in sc
            assert sc["readOnlyRootFilesystem"] is True

    def test_openshift_disabled_logging_sidecar_securitycontext_keeps_runasuser(self, kube_version):
        """Off OpenShift the logging-sidecar securityContext renders runAsUser unchanged."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"openshift": {"enabled": False}},
                "astronomer": {
                    "houston": {
                        "logging": {
                            "loggingSidecar": {
                                "enabled": True,
                                "cloudwatch": {"enabled": True},
                                "securityContext": {"runAsUser": 1234},
                            },
                        },
                    },
                },
            },
            show_only=[
                "charts/astronomer/templates/houston/api/houston-deployment.yaml",
                "charts/astronomer/templates/houston/worker/houston-worker-deployment.yaml",
            ],
        )

        assert len(docs) == 2
        for doc in docs:
            sc = get_containers_by_name(doc)["vector"]["securityContext"]
            assert sc["runAsUser"] == 1234
            assert sc["readOnlyRootFilesystem"] is True


# Templates that only render in the data plane; render them with plane.mode=data so the
# enumeration below actually produces pod managers to inspect. Mirrors test_byo_sa.py.
data_plane_only_template_substrings = (
    "nginx-dp-deployment",
    "prometheus-federation-auth-deployment",
    "pilot-deployment",
    "external-secrets",
    "commander-jwks-hooks",
)

# "Kind/release-name-workload/container": reason it may keep runAsUser on OpenShift.
# Privileged host daemons that must run as root, and vendored sub-charts whose securityContext
# we do not template. Add here only when a container genuinely cannot defer its UID to the SCC.
containers_allowed_to_pin_runasuser = {
    "DaemonSet/release-name-containerd-ca-update/cert-copy-and-toml-update": "privileged host daemon; runs as root (uid 0) to write CA certs to the host",
    "DaemonSet/release-name-vector/vector": "log collector; runs as root (uid 0) to read host log files",
    "Deployment/release-name-elasticsearch-client/sysctl": "privileged init container; runs as root (uid 0) to set vm.max_map_count",
    "StatefulSet/release-name-elasticsearch-data/sysctl": "privileged init container; runs as root (uid 0) to set vm.max_map_count",
    "StatefulSet/release-name-elasticsearch-master/sysctl": "privileged init container; runs as root (uid 0) to set vm.max_map_count",
    "Deployment/release-name-elasticsearch-exporter/metrics-exporter": "vendored elasticsearch-exporter sub-chart; securityContext not templated",
    "Deployment/release-name-elasticsearch-nginx/nginx": "vendored elasticsearch nginx sub-chart; securityContext not templated",
}


@pytest.mark.parametrize("template_name", find_all_pod_manager_templates())
def test_all_containers_omit_runasuser_on_openshift(template_name):
    """On OpenShift the SCC assigns each container's UID, so no container securityContext may
    pin runAsUser when global.openshift.enabled is True. Enforce this across every pod manager
    template in the chart (init containers included).
    """
    overrides = {"global": {"openshift": {"enabled": True}, "networkNSLabels": {"enabled": True}}}
    if any(substring in template_name for substring in data_plane_only_template_substrings):
        overrides["global"]["plane"] = {"mode": "data"}
    values = always_merger.merge(get_all_features(), overrides)

    docs = [doc for doc in render_chart(show_only=template_name, values=values) if doc["kind"] in pod_managers]
    for doc in docs:
        doc_id = f"{doc['kind']}/{doc['metadata']['name']}"
        for container_name, container in get_containers_by_name(doc, include_init_containers=True).items():
            key = f"{doc_id}/{container_name}"
            if key in containers_allowed_to_pin_runasuser:
                continue
            sc = container.get("securityContext") or {}
            assert "runAsUser" not in sc, (
                f"{key} (from {template_name}) pins runAsUser on OpenShift; the SCC must assign "
                f"the UID. If this is intentional, add it to containers_allowed_to_pin_runasuser "
                f"with a reason."
            )
