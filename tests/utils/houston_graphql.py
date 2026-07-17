"""Drive Houston's GraphQL API and wait on the Airflow Deployments it creates, from
inside a functional-test pod exec.

Shared by tests/functional/scenarios/deployment-lifecycle and
tests/functional/scenarios/auth-sidecar -- both create/upgrade a real Airflow
Deployment through Houston, not just install the platform chart.
"""

import json
import time

HOUSTON_URL = "http://localhost:8871/v1"


class HoustonError(RuntimeError):
    """Raised when Houston's GraphQL API returns a non-empty errors[] array."""


def dump_pod_logs(k8s_core_v1_client, label_selector: str, namespace: str = "astronomer", tail_lines: int = 200) -> None:
    """
    Print recent logs for every container in every pod matching label_selector.

    upsertDeployment's GraphQL error messages (e.g. "13 INTERNAL: failed to validate
    token") come from Commander over gRPC and are often too generic to diagnose on
    their own -- the real detail is in Commander's (or Houston's) own logs, and this
    devcontainer has no live cluster to inspect them by hand.
    """
    pods = k8s_core_v1_client.list_namespaced_pod(namespace, label_selector=label_selector).items
    if not pods:
        print(f"dump_pod_logs: no pods found for {namespace}/{label_selector}")
        return
    for pod in pods:
        for container in pod.spec.containers:
            print(f"--- logs: {namespace}/{pod.metadata.name} ({container.name}), last {tail_lines} lines ---")
            try:
                logs = k8s_core_v1_client.read_namespaced_pod_log(
                    pod.metadata.name, namespace, container=container.name, tail_lines=tail_lines
                )
                print(logs)
            except Exception as exc:  # noqa: BLE001
                print(f"(failed to fetch logs for {pod.metadata.name}/{container.name}: {exc})")


# houston-api's Alpine-based image only has curl as a build-time dependency -- it's
# removed via `apk del .build-deps` before the final image layer (see its Dockerfile).
# Node (the app's own runtime, guaranteed present) has a built-in global fetch since
# v18, so this shells out to `node -e` instead of relying on any HTTP client binary.
# Deliberately doesn't check response.ok: Houston can return GraphQL error detail in
# the JSON body on a non-2xx response, and fetch() only rejects on network failures,
# not on non-2xx status -- exactly the behavior needed here.
_GRAPHQL_NODE_SCRIPT = (
    "const [payload, token] = process.argv.slice(1);"
    "const headers = {'Content-Type': 'application/json'};"
    "if (token) headers['Authorization'] = 'Bearer ' + token;"
    f"fetch('{HOUSTON_URL}', {{method: 'POST', headers, body: payload}})"
    ".then(r => r.text()).then(t => process.stdout.write(t))"
    ".catch(e => { process.stderr.write(String(e)); process.exitCode = 1; });"
)


def graphql(houston_api, query: str, variables: dict | None = None, token: str | None = None) -> dict:
    """
    Execute a GraphQL request against Houston from inside the houston-api pod.

    The pytest process has no direct network path into the kind cluster's pod network --
    the same reason every fixture in conftest.py execs into a pod rather than connecting
    directly -- so this runs from inside the houston-api container itself.
    """
    payload = json.dumps({"query": query, "variables": variables or {}})
    output = houston_api.check_output("node -e %s %s %s", _GRAPHQL_NODE_SCRIPT, payload, token or "")
    body = json.loads(output)
    if body.get("errors"):
        messages = "; ".join(e.get("message", str(e)) for e in body["errors"])
        raise HoustonError(messages)
    return body["data"]


def create_user(houston_api, email: str, password: str) -> str:
    """Create the initial admin user. Only succeeds unauthenticated on a fresh DB -- true
    for every scenario's CircleCI job, since each one installs into a brand new cluster."""
    query = """
    mutation CreateUser($email: String!, $password: String!) {
      createUser(email: $email, password: $password) {
        token { value }
      }
    }
    """
    data = graphql(houston_api, query, {"email": email, "password": password})
    token = data["createUser"]["token"]["value"]
    assert token, "createUser returned an empty token value"
    return token


def create_workspace(houston_api, token: str, label: str) -> str:
    query = """
    mutation CreateWorkspace($label: String!) {
      createWorkspace(label: $label) { id }
    }
    """
    data = graphql(houston_api, query, {"label": label}, token=token)
    return data["createWorkspace"]["id"]


def get_cluster_id(houston_api, token: str) -> str:
    """Look up the default Cluster houston-api's populate-default-cluster script creates
    on startup in unified mode. No registerCluster call is needed for this topology."""
    query = "query ListClusters { paginatedClusters { clusters { id } } }"
    data = graphql(houston_api, query, token=token)
    clusters = data["paginatedClusters"]["clusters"]
    assert clusters, "Expected populate-default-cluster to have created a default Cluster in unified mode"
    return clusters[0]["id"]


def upsert_deployment(
    houston_api,
    token: str,
    *,
    executor: str,
    label: str | None = None,
    workspace_id: str | None = None,
    cluster_id: str | None = None,
    dag_deployment_type: str = "image",
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
                "label": label,
                "workspaceUuid": workspace_id,
                "clusterId": cluster_id,
                "dagDeployment": {"type": dag_deployment_type},
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
    data = graphql(houston_api, query, variables, token=token)
    return data["upsertDeployment"]


def dump_release_diagnostics(k8s_core_v1_client, namespace: str, label_selector: str) -> None:
    """
    Print actual Pod status and namespace Events for a release that never became ready.

    A Deployment's readyReplicas alone can't distinguish two very different failures:
    a pod Pod Security Admission rejects is never created at all -- it never becomes an
    unhealthy Pod, it only ever shows up as a FailedCreate Event on its ReplicaSet -- vs.
    a pod that *was* created but is stuck (image pull, crash loop, unschedulable). This
    prints both so the two aren't confused (see PINF-1031's auth-sidecar scenario for the
    same distinction at the single-Deployment level).
    """
    pods = k8s_core_v1_client.list_namespaced_pod(namespace, label_selector=label_selector).items
    if not pods:
        print(f"dump_release_diagnostics: no pods exist at all in {namespace} for {label_selector}")
    for pod in pods:
        statuses = [f"{c.name}: ready={c.ready} state={c.state}" for c in pod.status.container_statuses or []]
        print(
            f"pod {namespace}/{pod.metadata.name}: phase={pod.status.phase} -- {'; '.join(statuses) or 'no container statuses yet'}"
        )

    events = k8s_core_v1_client.list_namespaced_event(namespace).items
    print(f"--- events in {namespace} ({len(events)}) ---")
    for event in events:
        obj = event.involved_object
        print(f"{event.type} {event.reason}: {obj.kind}/{obj.name}: {event.message}")


def wait_for_release_ready(k8s_apps_v1_client, k8s_core_v1_client, release_name: str, timeout: int = 600) -> None:
    """
    Wait for every Deployment/StatefulSet Commander created for this release to reach
    readyReplicas == spec.replicas. Not just "pod visible" -- a rejected or
    not-yet-scheduled pod never shows up as unhealthy, only as missing.

    Prints progress every iteration, deliberately: CircleCI kills a job after 10
    minutes with no output at all, which is the same order of magnitude as this
    function's own timeout -- a silent poll loop risks CI killing the job before this
    function's own TimeoutError (with the actually useful detail) ever gets to fire.
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
            print(f"Release {release_name!r}: all {len(workloads)} Deployment(s)/StatefulSet(s) ready.")
            return
        if not workloads:
            not_ready = [f"no Deployments/StatefulSets found yet with label {label_selector}"]
        remaining = int(deadline - time.monotonic())
        print(f"Release {release_name!r} not ready yet ({remaining}s remaining): {', '.join(not_ready)}")
        if time.monotonic() >= deadline:
            namespace = workloads[0].metadata.namespace if workloads else None
            if namespace:
                dump_release_diagnostics(k8s_core_v1_client, namespace, label_selector)
            else:
                print(
                    f"dump_release_diagnostics: no Deployments/StatefulSets ever appeared for {label_selector}, can't determine namespace"
                )
            raise TimeoutError(f"Release {release_name!r} never became fully ready: {', '.join(not_ready)}")
        time.sleep(10)
