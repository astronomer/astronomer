"""Verifies the platform installs and runs on a real OpenShift API server.

test_profile.yaml sets cluster_provider: openshift, so the cluster is MicroShift rather than
KIND and these tests only read the result of that install.

What KIND cannot tell us: SecurityContextConstraints do not exist there, so nothing checks that
the platform's pods still fit OpenShift's restricted profile -- and a pod admitted by the wrong
SCC is Running like any other, so helm-install.py's pod-phase wait never notices.
"""

import re

import pytest
import testinfra
from kubernetes import client, config

from tests.utils.houston_graphql import (
    HoustonError,
    create_user,
    create_workspace,
    dump_pod_logs,
    get_cluster_id,
    upsert_deployment,
    wait_for_release_ready,
)
from tests.utils.k8s import KUBECONFIG_UNIFIED, find_admission_rejection_events, get_pod_by_label_selector

NAMESPACE = "astronomer"

# Written onto the pod at admission, so its presence proves SCC admission ran and its value says
# which constraint was used.
SCC_ANNOTATION = "openshift.io/scc"

# Both names, because which is the default is a property of the cluster's OpenShift version:
# restricted-v2 on anything current, restricted on older ones.
RESTRICTED_SCCS = frozenset({"restricted-v2", "restricted"})
AUTH_PROXY_CONTAINER = "auth-proxy"
GRAFANA_DEPLOYMENT_NAME = "astronomer-grafana"
ADMIN_EMAIL = "openshift-scenario-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "openshift-auth-sidecar"
DEPLOYMENT_LABEL = "openshift-auth-sidecar"
AUTH_PROXY_COMPONENTS_DAG_DEPLOY = frozenset({"webserver", "flower", "dag-server"})

# PINF-1049: commander's first JWKS fetch can race Houston's readiness. Transient, not a regression.
JWKS_COLD_START_ERROR = "13 INTERNAL: failed to validate token"


@pytest.fixture(scope="module")
def core_client() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def platform_pods(core_client) -> list:
    """Live pods in the platform namespace; one mid-deletion is from a revision on its way out."""
    pods = [pod for pod in core_client.list_namespaced_pod(NAMESPACE).items if pod.metadata.deletion_timestamp is None]
    assert pods, f"No pods at all in the {NAMESPACE} namespace -- the chart install cannot have succeeded"
    return pods


def test_no_admission_rejection_events(core_client):
    """Nothing was refused admission while the chart installed.

    A rejected pod is never created, so it leaves no unhealthy Pod object -- only a FailedCreate
    Warning on whatever tried. Empty name prefix: every one in the namespace matters here.
    """
    rejections = find_admission_rejection_events(core_client, NAMESPACE, "")
    assert not rejections, "Admission refused at least one platform pod:\n" + "\n".join(f"  {line}" for line in rejections)


def test_every_pod_runs_under_a_restricted_scc(platform_pods):
    """Every platform pod was admitted under a built-in restricted SCC.

    The platform's pods satisfy restricted-v2 as they are, and with global.openshift.enabled as
    the whole configuration that is all they get. A pod spec that gains a hostPath, a fixed uid
    or a privileged container has to be fixed in the spec, and this is what notices.

    Read from the pod, not from the SCC objects: what matters is which constraint OpenShift chose.
    """
    elevated = {
        pod.metadata.name: (pod.metadata.annotations or {}).get(SCC_ANNOTATION)
        for pod in platform_pods
        if (pod.metadata.annotations or {}).get(SCC_ANNOTATION) not in RESTRICTED_SCCS
    }
    assert not elevated, (
        f"These pods were not admitted by one of {sorted(RESTRICTED_SCCS)} (pod: {SCC_ANNOTATION}). "
        "None means SCC admission never saw the pod -- is this really an OpenShift cluster? Any "
        f"other name means it needs an elevated SCC: {elevated}"
    )


def test_bundled_nginx_is_not_deployed(core_client):
    """The chart's own ingress controller is off, leaving the cluster's router to front the platform.

    Left on, it would also fight openshift-ingress for host ports 80/443.
    """
    nginx_pods = sorted(
        pod.metadata.name
        for pod in core_client.list_namespaced_pod(NAMESPACE, label_selector="component=cp-ingress-controller").items
    )
    assert not nginx_pods, (
        "global.nginx.enabled should be false on OpenShift (configs/openshift.yaml), but the bundled "
        f"ingress controller is running: {', '.join(nginx_pods)}"
    )


def test_grafana_deployment_reaches_ready(k8s_apps_v1_client):
    """Ported from the auth-sidecar scenario, where it guards the same failure.

    A pod that admission rejects is never created, so it is missing rather than unhealthy --
    which readyReplicas == spec.replicas catches and a pod-by-pod check cannot. Here the
    rejection would come from an SCC the auth-proxy does not satisfy rather than from PSA.
    """
    deployment = k8s_apps_v1_client.read_namespaced_deployment(GRAFANA_DEPLOYMENT_NAME, NAMESPACE)
    desired = deployment.spec.replicas
    ready = deployment.status.ready_replicas or 0
    assert ready == desired, (
        f"{GRAFANA_DEPLOYMENT_NAME} has {ready}/{desired} ready replicas. Check for FailedCreate "
        "events on its ReplicaSet -- a rejected pod never becomes a Pod object, so it shows up as "
        "missing, not unhealthy."
    )


def test_grafana_has_auth_proxy_container(k8s_apps_v1_client):
    """Ported from the auth-sidecar scenario: global.authSidecar.enabled reached the pod spec.

    Read from the Deployment's template rather than a live pod, so it holds even when no pod was
    created -- which is the case the readiness check above exists for.
    """
    deployment = k8s_apps_v1_client.read_namespaced_deployment(GRAFANA_DEPLOYMENT_NAME, NAMESPACE)
    container_names = [container.name for container in deployment.spec.template.spec.containers]
    assert AUTH_PROXY_CONTAINER in container_names, f"Expected an auth-proxy container, got: {container_names}"


@pytest.fixture(scope="module")
def apps_client() -> client.AppsV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def houston_api():
    """Module-scoped Houston exec host; conftest.py's own fixture is function-scoped."""
    pod = get_pod_by_label_selector(NAMESPACE, "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={NAMESPACE}", kubeconfig=KUBECONFIG_UNIFIED)


@pytest.fixture(scope="module")
def deployment(houston_api, apps_client, core_client) -> dict:
    """One real Airflow Deployment, dag_deploy so dag-server and its own sidecar exist too.

    Ported from the auth-sidecar scenario, minus its git_sync stage: this runs the deployment
    under OpenShift's SCC admission rather than under a PSS-Restricted namespace.
    """
    token = create_user(houston_api, ADMIN_EMAIL, ADMIN_PASSWORD)
    workspace_id = create_workspace(houston_api, token, WORKSPACE_LABEL)
    cluster_id = get_cluster_id(houston_api, token)
    try:
        created = upsert_deployment(
            houston_api,
            token,
            executor="CeleryExecutor",
            label=DEPLOYMENT_LABEL,
            workspace_id=workspace_id,
            cluster_id=cluster_id,
            dag_deployment_type="dag_deploy",
        )
    except HoustonError:
        dump_pod_logs(core_client, "component=houston")
        dump_pod_logs(core_client, "component=commander")
        raise
    wait_for_release_ready(apps_client, core_client, created["releaseName"])
    return {"token": token, "id": created["id"], "release_name": created["releaseName"]}


@pytest.mark.flaky(reruns=5, reruns_delay=5, only_rerun=[JWKS_COLD_START_ERROR])
def test_deployment_reaches_ready(deployment):
    """The fixture already waits for readiness; this asserts that contract as its own named test.

    A sidecar the SCC will not admit shows up here, as pods that never reach ready.
    """
    assert deployment["release_name"]


def _pod_component(pod, release_name: str) -> str:
    """A pod's `component` label, or its name with the release prefix and replica suffix stripped."""
    label = (pod.metadata.labels or {}).get("component")
    if label:
        return label
    name = pod.metadata.name.removeprefix(f"{release_name}-")
    return re.sub(r"-[a-z0-9]{7,10}-[a-z0-9]{5}$|-[0-9]+$", "", name)


def test_deployment_has_auth_proxy_containers(deployment, core_client):
    """The auth sidecar reached the deployment's own namespace, not just the platform's."""
    release_name = deployment["release_name"]
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    injected = {
        _pod_component(pod, release_name)
        for pod in pods
        if any(container.name == AUTH_PROXY_CONTAINER for container in pod.spec.containers)
    }
    assert injected == AUTH_PROXY_COMPONENTS_DAG_DEPLOY, (
        f"Set of pods carrying an auth-proxy container changed for release {release_name!r} -- "
        "re-confirm the authSidecar wiring, then update the expected set only if the change is intended.\n"
        f"  expected:             {sorted(AUTH_PROXY_COMPONENTS_DAG_DEPLOY)}\n"
        f"  actual:               {sorted(injected)}\n"
        f"  unexpectedly present: {sorted(injected - AUTH_PROXY_COMPONENTS_DAG_DEPLOY)}\n"
        f"  unexpectedly missing: {sorted(AUTH_PROXY_COMPONENTS_DAG_DEPLOY - injected)}"
    )
