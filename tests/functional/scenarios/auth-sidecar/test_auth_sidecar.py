"""PINF-1031: catches the class of regression in PINF-1033 (a PSS-Restricted hardening
change broke global.authSidecar, not caught until QA). See test_profile.yaml for why
this scenario combines authSidecar with a PSS-Restricted-enforcing namespace rather
than testing them separately.

test_grafana_* covers the platform-namespace tier (astronomer chart: grafana,
alertmanager, prometheus). test_deployment_* and test_git_sync_deployment_* cover
the OTHER two authSidecar implementations that live in Airflow-Deployment-namespace
territory and were previously untestable here at all -- no scenario created a real
Airflow Deployment before PINF-1035 built the mechanism this reuses: houston-api's
server-side extraContainers() injection onto the deployment's own pods (via
dagDeployment.type: dag_deploy, which also turns on dag-server's own auth-sidecar
consumer -- see dag-server-auth-sidecar-configmap.yaml's `and .Values.dagDeploy.enabled
.Values.authSidecar.enabled` gate), and airflow-chart's git-sync-relay (via
dagDeployment.type: git_sync, authType: HTTPS_NONE, pointed at
astronomer/apc-test-dags-public -- a small public no-auth fixture repo, chosen
specifically so this doesn't need real git credentials in CI). All three
authSidecar implementations are now exercised here.
"""

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
from tests.utils.k8s import KUBECONFIG_UNIFIED, get_pod_by_label_selector

GRAFANA_DEPLOYMENT_NAME = "astronomer-grafana"
NAMESPACE = "astronomer"
ADMIN_EMAIL = "pinf-1031-auth-sidecar-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "pinf-1031-auth-sidecar"
DEPLOYMENT_LABEL = "pinf-1031-auth-sidecar"
# Distinct email/workspace from the dag_deploy deployment above -- both fixtures are
# module-scoped and independently self-contained (each creates its own user +
# workspace), and createUser rejects a duplicate email, so these can't be shared.
GIT_SYNC_ADMIN_EMAIL = "pinf-1031-auth-sidecar-git-sync-test@astronomer.io"
GIT_SYNC_WORKSPACE_LABEL = "pinf-1031-auth-sidecar-git-sync"
GIT_SYNC_DEPLOYMENT_LABEL = "pinf-1031-auth-sidecar-git-sync"
GIT_SYNC_REPOSITORY_URL = "https://github.com/astronomer/apc-test-dags-public"


def test_grafana_deployment_reaches_ready(k8s_apps_v1_client):
    """
    A pod Pod Security Admission rejects is never created -- it never becomes an
    unhealthy Pod object, it surfaces as a FailedCreate event on the Deployment's
    ReplicaSet. Asserting readyReplicas == spec.replicas (rather than "every visible
    pod is healthy") is what actually catches a rejected auth-proxy container.
    """
    deployment = k8s_apps_v1_client.read_namespaced_deployment(GRAFANA_DEPLOYMENT_NAME, NAMESPACE)
    desired = deployment.spec.replicas
    ready = deployment.status.ready_replicas or 0
    assert ready == desired, (
        f"{GRAFANA_DEPLOYMENT_NAME} has {ready}/{desired} ready replicas. Check for "
        "FailedCreate events on its ReplicaSet -- a pod rejected by Pod Security "
        "Admission never becomes a Pod object, so it shows up as missing, not unhealthy."
    )


def test_grafana_has_auth_proxy_container(k8s_apps_v1_client):
    """Confirms global.authSidecar.enabled actually wired the auth-proxy container into the pod spec."""
    deployment = k8s_apps_v1_client.read_namespaced_deployment(GRAFANA_DEPLOYMENT_NAME, NAMESPACE)
    container_names = [c.name for c in deployment.spec.template.spec.containers]
    assert "auth-proxy" in container_names, f"Expected an auth-proxy container, got: {container_names}"


@pytest.fixture(scope="module")
def _k8s_apps_v1_client_module() -> client.AppsV1Api:
    """Module-scoped so the deployment fixture below (also module-scoped, to avoid paying
    for a fresh Airflow Deployment per test) can depend on it -- conftest.py's own
    k8s_apps_v1_client is function-scoped and can't be used by a module-scoped fixture."""
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def _k8s_core_v1_client_module() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def _houston_api_module():
    """Module-scoped counterpart to conftest.py's houston_api fixture, for the same
    reason as _k8s_apps_v1_client_module above."""
    pod = get_pod_by_label_selector(NAMESPACE, "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={NAMESPACE}", kubeconfig=KUBECONFIG_UNIFIED)


@pytest.fixture(scope="module")
def deployment(_houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """
    Creates a real Airflow Deployment (dagDeployment.type: dag_deploy, so dag-server
    -- and its own auth-sidecar consumer -- gets created too) under this scenario's
    PSS-Restricted + authSidecar overlays, and waits for it to reach full readiness.
    """
    token = create_user(_houston_api_module, ADMIN_EMAIL, ADMIN_PASSWORD)
    workspace_id = create_workspace(_houston_api_module, token, WORKSPACE_LABEL)
    cluster_id = get_cluster_id(_houston_api_module, token)
    try:
        created = upsert_deployment(
            _houston_api_module,
            token,
            executor="CeleryExecutor",
            label=DEPLOYMENT_LABEL,
            workspace_id=workspace_id,
            cluster_id=cluster_id,
            dag_deployment_type="dag_deploy",
        )
    except HoustonError:
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"])
    return {"token": token, "id": created["id"], "release_name": created["releaseName"]}


def test_deployment_reaches_ready(deployment):
    """
    The deployment fixture already waits for readiness under PSS-Restricted -- this
    test asserts that contract explicitly. This is the "airflow pods ran into errors"
    gap: PINF-1033-class regressions in houston-api's or airflow-chart's own
    authSidecar injection show up here as pods that never reach ready, the same way a
    rejected container shows up as missing rather than unhealthy (see
    test_grafana_deployment_reaches_ready above).
    """
    assert deployment["release_name"]


def test_deployment_has_auth_proxy_containers(deployment, _k8s_core_v1_client_module):
    """
    Confirms authSidecar actually reached the Airflow-Deployment-namespace tier, not
    just the platform namespace test_grafana_has_auth_proxy_container already covers.
    Checks across every pod in the release rather than one hardcoded pod name, since
    which pod carries houston-api's injected auth-proxy (webserver vs. api-server)
    depends on the Astro Runtime version, and dag-server's copy is a second,
    independently-injected container this scenario now also exercises.
    """
    pods = _k8s_core_v1_client_module.list_pod_for_all_namespaces(label_selector=f"release={deployment['release_name']}").items
    assert pods, f"Expected at least one pod for release {deployment['release_name']!r}"
    containers_by_pod = {pod.metadata.name: [c.name for c in pod.spec.containers] for pod in pods}
    pods_with_auth_proxy = [name for name, containers in containers_by_pod.items() if "auth-proxy" in containers]
    assert pods_with_auth_proxy, f"Expected at least one pod with an auth-proxy container, got: {containers_by_pod}"


@pytest.fixture(scope="module")
def git_sync_deployment(_houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """
    Creates a second, separate Airflow Deployment (dagDeployment.type: git_sync) to
    exercise git-sync-relay -- the third and last authSidecar consumer, previously
    undocumented as a gap rather than fixed (see module docstring). A real, reachable
    repo is required, not just a syntactically-valid URL: git-sync-relay's git-daemon
    container's readiness/liveness/startup probes all check for a file a real clone
    creates (`.git/git-daemon-export-ok`), so an unreachable URL would hang the same
    way an earlier version of this scenario's own readiness wait once did (see
    wait_for_release_ready). astronomer/apc-test-dags-public is a small, public,
    Astronomer-owned fixture repo made for exactly this -- authType HTTPS_NONE, no
    credentials needed, and it's reachable from any CI runner the same way CI already
    reaches GitHub for its own checkout.
    """
    token = create_user(_houston_api_module, ADMIN_EMAIL, ADMIN_PASSWORD)
    workspace_id = create_workspace(_houston_api_module, token, WORKSPACE_LABEL)
    cluster_id = get_cluster_id(_houston_api_module, token)
    try:
        created = upsert_deployment(
            _houston_api_module,
            token,
            executor="CeleryExecutor",
            label=GIT_SYNC_DEPLOYMENT_LABEL,
            workspace_id=workspace_id,
            cluster_id=cluster_id,
            dag_deployment_type="git_sync",
            repository_url=GIT_SYNC_REPOSITORY_URL,
            auth_type="HTTPS_NONE",
        )
    except HoustonError:
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"])
    return {"token": token, "id": created["id"], "release_name": created["releaseName"]}


def test_git_sync_deployment_reaches_ready(git_sync_deployment):
    """
    Readiness here depends on git-sync-relay's git-daemon container actually cloning
    apc-test-dags-public successfully (its probes check for a post-clone marker file),
    so this also incidentally proves the repo choice is reachable from CI, not just
    that PSS-Restricted admits the pod.
    """
    assert git_sync_deployment["release_name"]


def test_git_sync_deployment_has_auth_proxy_container(git_sync_deployment, _k8s_core_v1_client_module):
    """
    Confirms authSidecar reached git-sync-relay's pod specifically -- the one
    implementation test_deployment_has_auth_proxy_containers above doesn't cover,
    since that fixture's dag_deploy deployment never creates a git-sync-relay pod at
    all (dag-server is a separate, independently-gated consumer).
    """
    pods = _k8s_core_v1_client_module.list_pod_for_all_namespaces(
        label_selector=f"release={git_sync_deployment['release_name']}"
    ).items
    assert pods, f"Expected at least one pod for release {git_sync_deployment['release_name']!r}"
    containers_by_pod = {pod.metadata.name: [c.name for c in pod.spec.containers] for pod in pods}
    pods_with_auth_proxy = [name for name, containers in containers_by_pod.items() if "auth-proxy" in containers]
    assert pods_with_auth_proxy, f"Expected at least one pod with an auth-proxy container, got: {containers_by_pod}"
