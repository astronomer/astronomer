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

    A "13 INTERNAL: failed to validate token" specifically is very likely PINF-1049,
    not a real regression. Confirmed via Commander's own logs on a real CI run: it's a
    literal TCP connection refusal when Commander fetches Houston's JWKS via the
    Service DNS name (`dial tcp ...:8871: connect: connection refused`), because
    Houston's pod hadn't been marked Ready by Kubernetes yet -- even though Houston's
    own app log already said "Server ready". This repo's own GraphQL calls succeed
    regardless, since they reach Houston via `kubectl exec` straight to its pod's
    localhost, bypassing the Service (and its Ready-endpoints-only routing) entirely --
    Commander has no such shortcut. This is Commander's first JWKS fetch racing ahead
    of Houston's own readiness gate during normal multi-pod bring-up, and
    fetchAndUpdateCache has no retry, so one connection refusal is treated as final.
    The fix belongs in commander (retry-with-backoff and/or single-flight around
    JWKS-fetching), not in this repo -- from here, re-running the CI job is the only
    available mitigation for this specific error message.
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


_PUBLIC_SIGNUPS_DISABLED_ERROR = "Public sign ups are disabled"


def create_user(houston_api, email: str, password: str) -> str:
    """Create the initial admin user, or log back in as one this same call already created.

    Public unauthenticated signup only ever succeeds ONCE per cluster -- true for every
    scenario's CircleCI job on a fresh install, but NOT safe to assume across a
    @pytest.mark.flaky(only_rerun=[...]) retry: pytest-rerunfailures reruns fixture setup, not
    just the test body, so a retry of the first test that touches a `deployment` fixture
    genuinely re-invokes create_user -- and by then this same call's own first attempt has
    already flipped signups off, so a second createUser for the identical email fails with
    "Public sign ups are disabled", not a benign no-op. Falling back to createToken (a normal
    login) on exactly that message makes this call idempotent across such a retry: the first
    attempt's user is still there, we just need a fresh token for it, not a new user.
    """
    try:
        data = graphql(
            houston_api,
            """
            mutation CreateUser($email: String!, $password: String!) {
              createUser(email: $email, password: $password) {
                token { value }
              }
            }
            """,
            {"email": email, "password": password},
        )
        token = data["createUser"]["token"]["value"]
    except HoustonError as exc:
        if _PUBLIC_SIGNUPS_DISABLED_ERROR not in str(exc):
            raise
        data = graphql(
            houston_api,
            """
            mutation LoginExistingUser($identity: String!, $password: String!) {
              createToken(identity: $identity, password: $password) {
                token { value }
              }
            }
            """,
            {"identity": email, "password": password},
        )
        token = data["createToken"]["token"]["value"]
    assert token, "create_user returned an empty token value"
    return token


_UNIQUE_WORKSPACE_LABEL_ERROR = "There is already another workspace with this label"


def create_workspace(houston_api, token: str, label: str) -> str:
    """Create a workspace, or look up the one this same call already created.

    Workspace labels must be unique (UniqueWorkspaceLabelError), so this hits the same
    retry-safety gap as create_user: a @pytest.mark.flaky(only_rerun=[...]) retry re-invokes
    fixture setup from scratch, and by then this exact label already exists from the first
    attempt. Falling back to the `workspaces(label: ...)` query on exactly that message looks up
    the existing workspace's id instead of trying (and failing) to create a second one.
    """
    try:
        data = graphql(
            houston_api,
            """
            mutation CreateWorkspace($label: String!) {
              createWorkspace(label: $label) { id }
            }
            """,
            {"label": label},
            token=token,
        )
        return data["createWorkspace"]["id"]
    except HoustonError as exc:
        if _UNIQUE_WORKSPACE_LABEL_ERROR not in str(exc):
            raise
        data = graphql(
            houston_api,
            """
            query FindWorkspaceByLabel($label: String) {
              workspaces(label: $label) { id }
            }
            """,
            {"label": label},
            token=token,
        )
        workspaces = data["workspaces"]
        assert workspaces, f"UniqueWorkspaceLabelError for {label!r} but workspaces(label=...) found none"
        return workspaces[0]["id"]


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
    dag_deployment_type: str | None = None,
    repository_url: str | None = None,
    auth_type: str | None = None,
    https_username: str | None = None,
    https_token: str | None = None,
    git_sync_repo_fetch_mode: str | None = None,
    environment_variables: list[dict] | None = None,
    deployment_uuid: str | None = None,
) -> dict:
    """
    Create (deployment_uuid=None) or update (deployment_uuid set) an Airflow Deployment.
    Same mutation both ways -- upsertDeployment resolves create vs. update from whether
    deployment_uuid identifies an existing row.

    dag_deployment_type is optional on update: passing it switches an existing
    deployment's DagDeploymentType (e.g. dag_deploy -> git_sync), the same way `executor`
    switches on an existing deployment_uuid -- houston-api has real handling for this
    (see getMungedArgs' gitSyncTransition logic, which strips stale git-sync fields when
    transitioning away from it). Omitting it on update leaves the stored dagDeployment
    config untouched. On create it defaults to "image" if not given.

    repository_url/auth_type only apply to dag_deployment_type="git_sync" (the DagDeployment
    fields git-sync-relay's own repositoryUrl/authType). auth_type (and https_username/
    https_token) are optional, not required, for git_sync: the DagDeployment input type only
    grew authType/httpsUsername/httpsToken in later houston-api releases for HTTPS+PAT auth --
    the houston-api version this chart currently pins (v2.0.37) has no such fields at all
    (git-sync there is SSH-key or public-HTTPS only, via repositoryUrl/knownHosts/sshKey), and
    sending authType against that schema fails server-side with a GraphQL "Field \"authType\"
    is not defined by type \"DagDeployment\"" error rather than anything this helper could
    validate locally. Omit auth_type entirely when targeting a schema that doesn't have it
    (e.g. a public repositoryUrl needs no credentials of any kind).

    environment_variables is [{"key": ..., "value": ..., "isSecret": bool}, ...] (isSecret
    optional). On update it's the one reliable way to FORCE Commander to actually re-render and
    re-apply a deployment's Helm values when nothing about the deployment's own upsert arguments
    changed -- e.g. after update_cluster has changed the config the deployment should now pick
    up. Deliberately not `upgradeDeployments`'s automatic post-upgrade hook Job for that: its
    `yarn upgrade-deployments` script publishes its NATS message with no globalDeploymentsConfig
    at all (see src/scripts/upgrade-deployments/index.js), and the consuming worker
    (deployment-upserted-for-update) reads globalDeploymentsConfig straight off that message with
    no fallback fetch -- so it always renders with the hardcoded default, never the deployment's
    actual current config, regardless of what changed.

    Note this alone is NOT enough to pick up a platform-level `houston.config.deployments.*`
    change made via a plain `helm upgrade` of the platform release: upsertDeployment's resolver
    does call gdc.get(...) fresh on every invocation, but gdc.get()'s Platform -> Cluster ->
    Workspace -> Deployment merge prefers the deployment's CLUSTER's own stored
    config.deployments over the live platform config whenever the cluster has one at all -- and
    every cluster does, because populate-default-cluster snapshots config.get("deployments") into
    the Cluster row once, at houston's first-ever startup, and never refreshes it. So a plain helm
    upgrade changes the live platform config but is invisible to any cluster that already existed
    before it ran. See update_cluster's docstring for the actual fix (updateCluster's
    deploymentsConfigOverride, merged straight into that stored config.deployments) -- do that
    first, then re-invoke upsertDeployment (this function) to make the deployment re-render
    against the now-updated cluster config.

    Validates label/workspace_id/cluster_id (on create) and repository_url (for git_sync)
    locally rather than letting a caller mistake reach Houston -- a missing required field
    surfaces there as a generic GraphQL/validation error with none of this helper's own
    context about *why* the field was required.
    """
    if not deployment_uuid and not (label and workspace_id and cluster_id):
        raise ValueError("Creating a deployment (no deployment_uuid) requires label, workspace_id, and cluster_id")
    if dag_deployment_type == "git_sync" and not repository_url:
        raise ValueError("dag_deployment_type='git_sync' requires repository_url")

    variables: dict = {"executor": executor}
    if deployment_uuid:
        variables["deploymentUuid"] = deployment_uuid
    else:
        variables.update({"label": label, "workspaceUuid": workspace_id, "clusterId": cluster_id})
        dag_deployment_type = dag_deployment_type or "image"

    if dag_deployment_type:
        dag_deployment = {"type": dag_deployment_type}
        if repository_url:
            dag_deployment["repositoryUrl"] = repository_url
        if auth_type:
            dag_deployment["authType"] = auth_type
        # HTTPS+PAT credentials (authType HTTPS_PAT). httpsToken is write-only server-side.
        if https_username:
            dag_deployment["httpsUsername"] = https_username
        if https_token:
            dag_deployment["httpsToken"] = https_token
        # git-sync fetch mode: "poll" (default) or "webhook". webhook mode makes the relay run a
        # webhook HTTP listener (which global.authSidecar then fronts with an auth-proxy sidecar);
        # no external webhook needs to be delivered for the relay to clone and become ready.
        if git_sync_repo_fetch_mode:
            dag_deployment["gitSyncRepoFetchMode"] = git_sync_repo_fetch_mode
        variables["dagDeployment"] = dag_deployment
    if environment_variables is not None:
        variables["environmentVariables"] = environment_variables
    query = """
    mutation UpsertDeployment(
      $label: String
      $workspaceUuid: Uuid
      $clusterId: Uuid
      $executor: ExecutorType
      $dagDeployment: DagDeployment
      $environmentVariables: [InputEnvironmentVariable]
      $deploymentUuid: Uuid
    ) {
      upsertDeployment(
        label: $label
        workspaceUuid: $workspaceUuid
        clusterId: $clusterId
        executor: $executor
        dagDeployment: $dagDeployment
        environmentVariables: $environmentVariables
        deploymentUuid: $deploymentUuid
      ) {
        id
        releaseName
      }
    }
    """
    data = graphql(houston_api, query, variables, token=token)
    return data["upsertDeployment"]


def validate_git_sync_credentials(
    houston_api,
    token: str,
    *,
    cluster_id: str,
    repository_url: str,
    https_token: str,
    https_username: str | None = None,
    deployment_uuid: str | None = None,
    workspace_uuid: str | None = None,
) -> dict:
    """Config-time git HTTPS+PAT credential validation (FR4.3): houston asks commander, in the
    target data plane, to reach repository_url and check the credentials. Returns
    {valid, category, message} where category is OK | AUTH_FAILED | UNREACHABLE | TLS_ERROR |
    INVALID_URL | TIMEOUT. clusterId is required by the schema; workspaceUuid/deploymentUuid only
    carry an entityId for the permission shield (pass one so an admin's RBAC check resolves)."""
    query = """
    mutation ValidateGitSyncCredentials(
      $clusterId: Uuid!
      $repositoryUrl: String!
      $httpsUsername: String
      $httpsToken: String!
      $deploymentUuid: Uuid
      $workspaceUuid: Uuid
    ) {
      validateGitSyncCredentials(
        clusterId: $clusterId
        repositoryUrl: $repositoryUrl
        httpsUsername: $httpsUsername
        httpsToken: $httpsToken
        deploymentUuid: $deploymentUuid
        workspaceUuid: $workspaceUuid
      ) {
        valid
        category
        message
      }
    }
    """
    variables = {
        "clusterId": cluster_id,
        "repositoryUrl": repository_url,
        "httpsUsername": https_username,
        "httpsToken": https_token,
        "deploymentUuid": deployment_uuid,
        "workspaceUuid": workspace_uuid,
    }
    return graphql(houston_api, query, variables, token=token)["validateGitSyncCredentials"]


def _summarize_pods(k8s_core_v1_client, namespace: str, label_selector: str) -> list[str]:
    """One line per pod matching label_selector: phase plus each container's ready/state.

    Shared by wait_for_release_ready's per-iteration status line (so a crash-looping
    container is visible on every poll, not just once the 600s timeout finally fires)
    and dump_release_diagnostics' fuller post-mortem below.
    """
    pods = k8s_core_v1_client.list_namespaced_pod(namespace, label_selector=label_selector).items
    if not pods:
        return [f"no pods exist yet in {namespace} for {label_selector}"]
    lines = []
    for pod in pods:
        statuses = [f"{c.name}: ready={c.ready} state={c.state}" for c in pod.status.container_statuses or []]
        lines.append(
            f"{namespace}/{pod.metadata.name}: phase={pod.status.phase} -- {'; '.join(statuses) or 'no container statuses yet'}"
        )
    return lines


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
    for line in _summarize_pods(k8s_core_v1_client, namespace, label_selector):
        print(f"pod {line}")

    events = k8s_core_v1_client.list_namespaced_event(namespace).items
    print(f"--- events in {namespace} ({len(events)}) ---")
    for event in events:
        obj = event.involved_object
        print(f"{event.type} {event.reason}: {obj.kind}/{obj.name}: {event.message}")


def _workload_settled(w) -> bool:
    """True when a Deployment/StatefulSet has fully rolled out its current spec and is ready: the
    controller has observed the latest generation, and every replica is updated, ready, and current
    with no surplus pod from a prior revision still terminating.

    Stronger than ready_replicas == spec.replicas alone, which can hold *mid-rollout*: during a
    RollingUpdate the old pod stays Ready until the new one is Ready, so ready_replicas can equal
    spec.replicas while the change is only half-applied. Requiring observed_generation to have caught
    up and updated_replicas == replicas == spec.replicas closes that gap.
    """
    spec_replicas = w.spec.replicas or 0
    status = w.status
    if status is None:
        return spec_replicas == 0
    if (status.observed_generation or 0) < (w.metadata.generation or 0):
        return False
    return (
        (status.ready_replicas or 0) == spec_replicas
        and (status.updated_replicas or 0) == spec_replicas
        and (status.replicas or 0) == spec_replicas
    )


def _workload_key(w) -> str:
    return f"{w.metadata.namespace}/{w.metadata.name}"


def snapshot_release_revisions(k8s_apps_v1_client, release_name: str) -> dict[str, int]:
    """Snapshot each of the release's current Deployments/StatefulSets to its metadata.generation.

    Take this BEFORE an upsertDeployment that mutates an existing release (an executor or
    dagDeploymentType switch), then pass it to wait_for_release_ready(previous_revisions=...).
    Commander applies the change asynchronously (NATS -> houston-worker -> commander -> helm
    upgrade), so without a baseline the pre-update workloads are still present and fully ready the
    instant the wait is called, and it returns immediately -- before the new topology (e.g. the
    git-sync relay a git_sync switch adds) exists. With the baseline, the wait blocks until the
    change is actually applied first. Omit it for a fresh create, which has no prior all-ready state.
    """
    label_selector = f"release={release_name}"
    deployments = k8s_apps_v1_client.list_deployment_for_all_namespaces(label_selector=label_selector).items
    statefulsets = k8s_apps_v1_client.list_stateful_set_for_all_namespaces(label_selector=label_selector).items
    return {_workload_key(w): (w.metadata.generation or 0) for w in deployments + statefulsets}


def _update_applied(current: dict[str, int], previous: dict[str, int]) -> bool:
    """True once the release's workloads differ from the pre-update snapshot -- a workload was added
    or removed, or an existing one's generation advanced (its spec changed) -- i.e. Commander has
    started applying the requested change rather than the old topology still standing untouched."""
    if set(current) != set(previous):
        return True
    return any(generation > previous.get(key, -1) for key, generation in current.items())


def wait_for_release_ready(
    k8s_apps_v1_client,
    k8s_core_v1_client,
    release_name: str,
    timeout: int = 600,
    *,
    previous_revisions: dict[str, int] | None = None,
) -> None:
    """
    Wait for every Deployment/StatefulSet Commander created for this release to finish rolling out
    its current spec and reach readiness. Not just "pod visible" -- a rejected or not-yet-scheduled
    pod never shows up as unhealthy, only as missing -- and not just ready_replicas == spec.replicas,
    which can hold mid-rollout while an old pod is still counted ready (see _workload_settled).

    On an UPDATE to an existing release (an executor switch, a dagDeploymentType switch), Commander
    applies the change asynchronously, so the pre-update workloads are still present and ready the
    instant this is called -- returning then inspects stale pods (this is how a git_sync switch could
    look "ready" with no relay pod, and how auth-sidecar's git_sync tests ended up observing the old
    dag-downloader sidecars). Pass previous_revisions (a snapshot_release_revisions() taken just
    before the upsert) so this first waits for the change to actually be applied. Omit it for a fresh
    create, which has no prior all-ready state to short-circuit on.

    Prints progress every iteration, deliberately: CircleCI kills a job after 10
    minutes with no output at all, which is the same order of magnitude as this
    function's own timeout -- a silent poll loop risks CI killing the job before this
    function's own TimeoutError (with the actually useful detail) ever gets to fire.

    Also prints per-pod container status every iteration, not just once at the final
    timeout -- this is intermittent (PINF-1068, PINF-1049 were both this shape: only
    some runs hit it), so a crash-looping sidecar or a JWKS race needs to be visible on
    the run that actually hits it, not only inferred after the fact from a rerun.
    """
    label_selector = f"release={release_name}"
    start = time.monotonic()
    deadline = start + timeout
    while True:
        deployments = k8s_apps_v1_client.list_deployment_for_all_namespaces(label_selector=label_selector).items
        statefulsets = k8s_apps_v1_client.list_stateful_set_for_all_namespaces(label_selector=label_selector).items
        workloads = deployments + statefulsets

        update_pending = previous_revisions is not None and not _update_applied(
            {_workload_key(w): (w.metadata.generation or 0) for w in workloads}, previous_revisions
        )
        not_ready = [
            f"{w.metadata.namespace}/{w.metadata.name} ({(w.status.ready_replicas or 0) if w.status else 0}/{w.spec.replicas})"
            for w in workloads
            if not _workload_settled(w)
        ]
        if workloads and not not_ready and not update_pending:
            print(
                f"Release {release_name!r}: all {len(workloads)} Deployment(s)/StatefulSet(s) ready "
                f"after {int(time.monotonic() - start)}s."
            )
            return
        if not workloads:
            not_ready = [f"no Deployments/StatefulSets found yet with label {label_selector}"]
        elif update_pending and not not_ready:
            not_ready = ["waiting for Commander to apply the requested update (topology still matches the pre-update snapshot)"]
        remaining = int(deadline - time.monotonic())
        elapsed = int(time.monotonic() - start)
        print(f"Release {release_name!r} not ready yet ({elapsed}s elapsed, {remaining}s remaining): {', '.join(not_ready)}")
        namespace = workloads[0].metadata.namespace if workloads else None
        if namespace:
            for line in _summarize_pods(k8s_core_v1_client, namespace, label_selector):
                print(f"  pod {line}")
        if time.monotonic() >= deadline:
            if namespace:
                dump_release_diagnostics(k8s_core_v1_client, namespace, label_selector)
            else:
                print(
                    f"dump_release_diagnostics: no Deployments/StatefulSets ever appeared for {label_selector}, can't determine namespace"
                )
            raise TimeoutError(f"Release {release_name!r} never became fully ready: {', '.join(not_ready)}")
        time.sleep(10)


def update_cluster(houston_api, token: str, *, cluster_id: str, deployments_config_override: dict) -> dict:
    """
    Merge deployments_config_override into a Cluster's stored config.deployments -- the tier
    gdc.get() actually reads (ahead of the live platform config) for every deployment on that
    cluster. See src/lib/clusters/index.js's updateCluster: it does
    `mergeConfigs(currentConfig=clusterDetails.config.deployments, overrideConfig=
    deployments_config_override)` and writes the result straight back to config.deployments (also
    separately recording the raw override under configOverride.deployments).

    This is the only way to make an ALREADY-REGISTERED cluster (e.g. the default cluster
    populate-default-cluster creates on houston's first startup in unified mode) pick up a
    houston.config.deployments.* change -- a plain `helm upgrade` of the platform release alone
    is not enough, because populate-default-cluster snapshots config.get("deployments") into the
    Cluster row exactly once, at first startup, and nothing ever refreshes it afterward (it's
    create-once: `if (cluster) return`). See upsert_deployment's docstring for the second half of
    this: this call alone doesn't touch any already-running deployment's actual Helm
    values -- follow it with an upsert_deployment call to force a re-render.
    """
    query = """
    mutation UpdateCluster($id: Uuid!, $deploymentsConfigOverride: JSON) {
      updateCluster(id: $id, deploymentsConfigOverride: $deploymentsConfigOverride) {
        id
      }
    }
    """
    variables = {"id": cluster_id, "deploymentsConfigOverride": deployments_config_override}
    data = graphql(houston_api, query, variables, token=token)
    return data["updateCluster"]


def get_effective_config(houston_api, token: str, deployment_uuid: str) -> dict:
    """
    Deployment.effectiveConfig: the final Platform -> Cluster -> Workspace -> Deployment merged
    config Houston actually renders this deployment's Helm values from.

    Much cheaper to assert against than inspecting live pod securityContexts, and narrows a
    failure to one of two very different causes: if effectiveConfig doesn't show the expected
    value, the config never reached this deployment (an update_cluster/gdc.get()-tier problem);
    if it does but a live pod still enforces readOnlyRootFilesystem, the config reached Houston
    fine but Commander/the chart didn't apply it (or the deployment hasn't been re-rendered since
    -- see upsert_deployment's environment_variables trick).
    """
    query = """
    query DeploymentEffectiveConfig($id: String!) {
      deployment(where: { id: $id }) {
        effectiveConfig
      }
    }
    """
    data = graphql(houston_api, query, {"id": deployment_uuid}, token=token)
    return data["deployment"]["effectiveConfig"]
