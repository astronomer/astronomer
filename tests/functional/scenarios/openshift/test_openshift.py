"""Verifies the platform installs and runs on a real OpenShift API server.

test_profile.yaml sets cluster_provider: openshift, so the cluster is MicroShift rather than
KIND and these tests only read the result of that install.

Mirrors the auth-sidecar scenario, minus its git_sync stage: the same two platform-tier grafana
checks, the same one Airflow Deployment, and the same assertions over its pods -- but with
OpenShift's SecurityContextConstraints as the admission control rather than a PSS-Restricted
namespace. A sidecar an SCC will not admit never becomes a Pod object, and a pod whose container
cannot start stays in phase Running, so helm-install.py's pod-phase wait sees neither.
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
AUTH_PROXY_CONTAINER = "auth-proxy"

# configs/openshift.yaml turns global.authSidecar on, because with the bundled nginx off the
# sidecar is what authenticates these endpoints. Grafana stands in for the platform tier, as in
# the auth-sidecar scenario: of the components that get a sidecar it is the only Deployment,
# alertmanager and prometheus being StatefulSets.
GRAFANA_DEPLOYMENT_NAME = "astronomer-grafana"

# The Airflow Deployment the tests below create, to reach the auth-sidecar consumers that live in
# the deployment's own namespace rather than the platform's. dag_deploy gets three: the web
# component and flower, injected server-side by houston-api, and dag-server's own copy from the
# chart. Asserted as an exact set -- a consumer silently losing its sidecar is the regression
# worth catching, and an at-least-one check sails past it.
ADMIN_EMAIL = "openshift-scenario-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "openshift-auth-sidecar"
DEPLOYMENT_LABEL = "openshift-auth-sidecar"
AUTH_PROXY_COMPONENTS_DAG_DEPLOY = frozenset({"webserver", "flower", "dag-server"})

# PINF-1049: commander's first JWKS fetch can race Houston's readiness. Transient, not a regression.
JWKS_COLD_START_ERROR = "13 INTERNAL: failed to validate token"


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


def test_bundled_nginx_is_not_deployed(k8s_core_v1_client):
    """The chart's own ingress controller is off, leaving the cluster's router to front the platform.

    Left on, it would also fight openshift-ingress for host ports 80/443.
    """
    nginx_pods = sorted(
        pod.metadata.name
        for pod in k8s_core_v1_client.list_namespaced_pod(NAMESPACE, label_selector="component=cp-ingress-controller").items
    )
    assert not nginx_pods, (
        "global.nginx.enabled should be false on OpenShift (configs/openshift.yaml), but the bundled "
        f"ingress controller is running: {', '.join(nginx_pods)}"
    )


@pytest.fixture(scope="module")
def core_client() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


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
def admin_token(houston_api) -> str:
    """Bootstrap the cluster's one and only admin.

    Its own fixture rather than a line inside `deployment`, because createUser's unauthenticated
    signup succeeds exactly once per cluster. pytest-rerunfailures drops the cached result of a
    fixture that raised, so a JWKS retry re-executes `deployment` -- and a createUser in there
    would meet "Public sign ups are disabled" instead of retrying what actually failed. This
    fixture succeeded, so its token stays cached across those reruns.
    """
    return create_user(houston_api, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def deployment(admin_token, houston_api, apps_client, core_client) -> dict:
    """One real Airflow Deployment, dag_deploy so dag-server and its own sidecar exist too.

    Ported from the auth-sidecar scenario, minus its git_sync stage: this runs the deployment
    under OpenShift's SCC admission rather than under a PSS-Restricted namespace.
    """
    token = admin_token
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


def _restricted_offenders(pods) -> dict[str, list[str]]:
    """Mirrors the auth-sidecar scenario's _pss_restricted_offenders, against live pods.

    Same properties, different enforcer: there the namespace's PSA labels require them, here
    OpenShift's restricted-v2 SCC does, and it goes further by assigning the uid rather than only
    requiring non-root. Worth asserting anyway, because admission proves what was *allowed* in,
    not what the SCC actually wrote -- and the auth-proxy is injected server-side by houston-api
    and the chart, so no chart-render test in any repo sees its securityContext.
    """
    offenders = {}
    for pod in pods:
        pod_sc = pod.spec.security_context
        pod_seccomp = pod_sc.seccomp_profile.type if pod_sc and pod_sc.seccomp_profile else None
        pod_run_as_user = pod_sc.run_as_user if pod_sc else None
        pod_run_as_non_root = pod_sc.run_as_non_root if pod_sc else None
        for container in list(pod.spec.containers) + list(pod.spec.init_containers or []):
            container_id = f"{pod.metadata.name}/{container.name}"
            sc = container.security_context
            if sc is None:
                offenders[container_id] = ["no securityContext set"]
                continue
            problems = []
            if sc.allow_privilege_escalation is not False:
                problems.append(f"allowPrivilegeEscalation={sc.allow_privilege_escalation!r}")
            if not sc.capabilities or "ALL" not in (sc.capabilities.drop or []):
                problems.append(f"capabilities.drop={getattr(sc.capabilities, 'drop', None)!r}")
            # Set at either the pod or the container level and inherited down.
            run_as_non_root = sc.run_as_non_root if sc.run_as_non_root is not None else pod_run_as_non_root
            if run_as_non_root is not True:
                problems.append(f"runAsNonRoot={run_as_non_root!r}")
            run_as_user = sc.run_as_user if sc.run_as_user is not None else pod_run_as_user
            if run_as_user in (None, 0):
                problems.append(f"runAsUser={run_as_user!r}")
            container_seccomp = sc.seccomp_profile.type if sc.seccomp_profile else None
            if "RuntimeDefault" not in (pod_seccomp, container_seccomp):
                problems.append(f"seccompProfile={container_seccomp!r} (pod-level: {pod_seccomp!r})")
            if problems:
                offenders[container_id] = problems
    return offenders


def test_deployment_pods_have_restricted_security_context(deployment, core_client):
    """Live-pod counterpart to test_deployment_reaches_ready -- see _restricted_offenders."""
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={deployment['release_name']}").items
    assert pods, f"Expected at least one pod for release {deployment['release_name']!r}"
    offenders = _restricted_offenders(pods)
    assert not offenders, "Containers without a full restricted securityContext (container: problems):\n" + "\n".join(
        f"  {key}: {value}" for key, value in sorted(offenders.items())
    )


def test_no_admission_rejection_events(core_client, deployment):
    """Check platform and Airflow namespaces for refused pod creation."""
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={deployment['release_name']}").items
    assert pods, f"Expected at least one pod for release {deployment['release_name']!r}"
    namespaces = {NAMESPACE} | {pod.metadata.namespace for pod in pods}
    rejections = [
        f"{namespace}: {line}"
        for namespace in sorted(namespaces)
        for line in find_admission_rejection_events(core_client, namespace, "")
    ]
    assert not rejections, "Admission refused at least one platform or Airflow pod:\n" + "\n".join(
        f"  {line}" for line in rejections
    )
