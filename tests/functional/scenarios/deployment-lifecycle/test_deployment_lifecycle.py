"""PINF-1035: creates a real Airflow Deployment through Houston's GraphQL API, then
switches its executor. Closes a gap no other functional test covers -- every other
scenario (including PINF-1031's auth-sidecar) only installs the platform chart, never
an Airflow Deployment on top of it.

Uses the GraphQL API deliberately, not Commander's gRPC interface directly (which
Commander's own component tests already exercise): GraphQL is the core API for the APC
app -- the UI and astro-cli go through it -- so testing through it exercises the actual
path a real customer takes (houston-api -> NATS JetStream -> houston-worker -> Commander
-> Helm), not just Commander's Helm-templating logic in isolation.

Doesn't reproduce PINF-1033 itself -- that bug was an OpenShift/ARO-SCC UID collision,
invisible to this kind-based CI by construction (see PINF-716/MV for that gap). This
catches Helm-values-assembly and upgrade-path regressions that break on any cluster,
generic or OpenShift alike.

Mutation shapes and the createUser-then-createWorkspace bootstrap sequence are ported
from software-upgrade-automation's bin/configure-k3d-for-tests.py and
bin/create-git-sync-deployment.py (QA's own k3d CP/DP test tooling), adapted for the
unified topology: no registerCluster call is needed here, because houston-api's
populate-default-cluster script already creates a default Cluster row on startup
whenever plane.mode is unified.
"""

import json
import time

import pytest
import testinfra
from kubernetes import client, config

from tests.utils.k8s import KUBECONFIG_UNIFIED, get_pod_by_label_selector

NAMESPACE = "astronomer"
HOUSTON_URL = "http://localhost:8871/v1"
ADMIN_EMAIL = "pinf-1035-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "pinf-1035"
DEPLOYMENT_LABEL = "pinf-1035-lifecycle"


class HoustonError(RuntimeError):
    """Raised when Houston's GraphQL API returns a non-empty errors[] array."""


def _graphql(houston_api, query: str, variables: dict | None = None, token: str | None = None) -> dict:
    """
    Execute a GraphQL request against Houston from inside the houston-api pod.

    The pytest process has no direct network path into the kind cluster's pod network --
    the same reason every fixture in conftest.py execs into a pod rather than connecting
    directly -- so this curls localhost from inside the houston-api container itself.
    Deliberately no `curl -f`: Houston can return GraphQL error detail in the JSON body
    on a non-2xx response, and `-f` would make curl fail before that body is readable.
    """
    payload = json.dumps({"query": query, "variables": variables or {}})
    command = f"curl -s -X POST {HOUSTON_URL} -H 'Content-Type: application/json'"
    if token:
        command += f" -H 'Authorization: Bearer {token}'"
    command += " --data %s"
    output = houston_api.check_output(command, payload)
    body = json.loads(output)
    if body.get("errors"):
        messages = "; ".join(e.get("message", str(e)) for e in body["errors"])
        raise HoustonError(messages)
    return body["data"]


def _create_user(houston_api, email: str, password: str) -> str:
    """Create the initial admin user. Only succeeds unauthenticated on a fresh DB -- true
    here, since each scenario's CircleCI job installs into a brand new kind cluster."""
    query = """
    mutation CreateUser($email: String!, $password: String!) {
      createUser(email: $email, password: $password) {
        token { value }
      }
    }
    """
    data = _graphql(houston_api, query, {"email": email, "password": password})
    token = data["createUser"]["token"]["value"]
    assert token, "createUser returned an empty token value"
    return token


def _create_workspace(houston_api, token: str, label: str) -> str:
    query = """
    mutation CreateWorkspace($label: String!) {
      createWorkspace(label: $label) { id }
    }
    """
    data = _graphql(houston_api, query, {"label": label}, token=token)
    return data["createWorkspace"]["id"]


def _get_cluster_id(houston_api, token: str) -> str:
    """Look up the default Cluster houston-api's populate-default-cluster script creates
    on startup in unified mode. No registerCluster call is needed for this topology."""
    query = "query ListClusters { paginatedClusters { clusters { id } } }"
    data = _graphql(houston_api, query, token=token)
    clusters = data["paginatedClusters"]["clusters"]
    assert clusters, "Expected populate-default-cluster to have created a default Cluster in unified mode"
    return clusters[0]["id"]


def _upsert_deployment(
    houston_api,
    token: str,
    *,
    executor: str,
    workspace_id: str | None = None,
    cluster_id: str | None = None,
    deployment_uuid: str | None = None,
) -> dict:
    """
    Create (deployment_uuid=None) or update (deployment_uuid set) an Airflow Deployment.
    Same mutation both ways -- upsertDeployment resolves create vs. update from whether
    deployment_uuid identifies an existing row.
    """
    variables: dict = {"executor": executor}
    if deployment_uuid:
        variables["deploymentUuid"] = deployment_uuid
    else:
        variables.update(
            {
                "label": DEPLOYMENT_LABEL,
                "workspaceUuid": workspace_id,
                "clusterId": cluster_id,
                "dagDeployment": {"type": "image"},
            }
        )
    query = """
    mutation UpsertDeployment(
      $label: String
      $workspaceUuid: Uuid
      $clusterId: Uuid
      $executor: ExecutorType
      $dagDeployment: DagDeployment
      $deploymentUuid: Uuid
    ) {
      upsertDeployment(
        label: $label
        workspaceUuid: $workspaceUuid
        clusterId: $clusterId
        executor: $executor
        dagDeployment: $dagDeployment
        deploymentUuid: $deploymentUuid
      ) {
        id
        releaseName
      }
    }
    """
    data = _graphql(houston_api, query, variables, token=token)
    return data["upsertDeployment"]


def _wait_for_release_ready(k8s_apps_v1_client, release_name: str, timeout: int = 600) -> None:
    """
    Wait for every Deployment/StatefulSet Commander created for this release to reach
    readyReplicas == spec.replicas. Not just "pod visible" -- see PINF-1031's auth-sidecar
    scenario for why that distinction matters: a rejected or not-yet-scheduled pod never
    shows up as unhealthy, only as missing.
    """
    label_selector = f"release={release_name}"
    deadline = time.monotonic() + timeout
    while True:
        deployments = k8s_apps_v1_client.list_deployment_for_all_namespaces(label_selector=label_selector).items
        statefulsets = k8s_apps_v1_client.list_stateful_set_for_all_namespaces(label_selector=label_selector).items
        workloads = deployments + statefulsets
        not_ready = [
            f"{w.metadata.namespace}/{w.metadata.name} ({w.status.ready_replicas or 0}/{w.spec.replicas})"
            for w in workloads
            if (w.status.ready_replicas or 0) != w.spec.replicas
        ]
        if workloads and not not_ready:
            return
        if not workloads:
            not_ready = [f"no Deployments/StatefulSets found yet with label {label_selector}"]
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Release {release_name!r} never became fully ready: {', '.join(not_ready)}")
        time.sleep(10)


@pytest.fixture(scope="module")
def _k8s_apps_v1_client_module() -> client.AppsV1Api:
    """Module-scoped so the deployment fixture below (also module-scoped, to avoid paying
    for a fresh Airflow Deployment per test) can depend on it -- conftest.py's own
    k8s_apps_v1_client is function-scoped and can't be used by a module-scoped fixture."""
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def _houston_api_module():
    """Module-scoped counterpart to conftest.py's houston_api fixture, for the same
    reason as _k8s_apps_v1_client_module above."""
    pod = get_pod_by_label_selector(NAMESPACE, "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={NAMESPACE}", kubeconfig=KUBECONFIG_UNIFIED)


@pytest.fixture(scope="module")
def deployment(_houston_api_module, _k8s_apps_v1_client_module):
    """
    Bootstraps a fresh admin user and workspace, creates an Airflow Deployment through
    Houston's GraphQL API, and waits for it to reach full readiness. Module-scoped: both
    tests in this file share the one deployment, since creating it is the expensive part
    and the switch test needs an already-ready deployment to switch.
    """
    token = _create_user(_houston_api_module, ADMIN_EMAIL, ADMIN_PASSWORD)
    workspace_id = _create_workspace(_houston_api_module, token, WORKSPACE_LABEL)
    cluster_id = _get_cluster_id(_houston_api_module, token)
    created = _upsert_deployment(
        _houston_api_module,
        token,
        executor="CeleryExecutor",
        workspace_id=workspace_id,
        cluster_id=cluster_id,
    )
    _wait_for_release_ready(_k8s_apps_v1_client_module, created["releaseName"])
    return {"token": token, "id": created["id"], "release_name": created["releaseName"]}


def test_deployment_reaches_ready(deployment):
    """The deployment fixture already waits for readiness -- this test asserts that
    contract explicitly, so a fixture-setup failure surfaces as a named test result
    rather than only as a collection error."""
    assert deployment["release_name"]


def test_deployment_survives_executor_switch(deployment, houston_api, k8s_apps_v1_client):
    """
    Exercises the failure class PINF-1033 was caught in: an Airflow Deployment upgrade
    that changes its executor. Re-invokes upsertDeployment on the same deployment_uuid,
    the same mutation Commander's own upgrade path uses.
    """
    _upsert_deployment(
        houston_api,
        deployment["token"],
        executor="KubernetesExecutor",
        deployment_uuid=deployment["id"],
    )
    _wait_for_release_ready(k8s_apps_v1_client, deployment["release_name"])
