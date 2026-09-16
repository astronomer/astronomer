"""Verifies the Houston loggingSidecar is wired correctly when enabled with a CUSTOM
config (global.logging.loggingSidecar.customConfig: true).

This scenario covers the log-shipping sidecar (global.logging.loggingSidecar.name, default
"sidecar-log-consumer") that Houston injects into each *Airflow deployment* pod it
provisions -- specifically its customConfig: true behavior.

customConfig: true behavior (houston-api src/lib/deployments/config/index.js ~L1423):
  Houston mounts the injected sidecar's config from a Secret named "sidecar-config"
  (a FIXED name, not release-prefixed) via a "config-volume" volume, instead of the
  default per-release ConfigMap "<releaseName>-sidecar-config". Houston only *references*
  the Secret -- it does not create it -- so the deployment fixture below provisions it in
  the deployment's namespace before the pods roll out.

The injected sidecar lands only on the log-producing Airflow components -- scheduler,
workers, triggerer, webserver (AF2) or apiserver (AF3), and dag-processor if enabled
(defaultComponents in the same houston-api file) -- NOT on every pod of the release
(pgbouncer, statsd, flower, redis, etc. do not get it). So the pod-level assertions here
scope to pods that actually carry the sidecar container rather than the whole release.

The create-deployment machinery mirrors the deployment-lifecycle and auth-sidecar
scenarios: a real Airflow Deployment built through Houston's GraphQL API (the path a
customer takes: houston-api -> NATS JetStream -> houston-worker -> Commander -> Helm).
"""

import time

import pytest
import testinfra
from kubernetes import client, config

from tests.utils.houston_graphql import (
    HoustonError,
    create_user,
    create_workspace,
    dump_pod_logs,
    get_cluster_id,
    snapshot_release_revisions,
    upsert_deployment,
    wait_for_release_ready,
)
from tests.utils.k8s import KUBECONFIG_UNIFIED, get_pod_by_label_selector

NAMESPACE = "astronomer"
ADMIN_EMAIL = "sidecar-logging-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "sidecar-logging"
DEPLOYMENT_LABEL = "sidecar-logging"

# A public, no-auth fixture repo
GIT_SYNC_REPOSITORY_URL = "https://github.com/astronomer/apc-test-dags-public"

# The EXACT set of pod `component` labels expected to carry the injected logging sidecar
STANDARD_SIDECAR_COMPONENTS = {"scheduler", "worker", "triggerer", "dag-processor", "api-server"}

# The two DagDeployment-specific consumers, each present only in its own type
DAG_SERVER_COMPONENT = "dag-server"
GIT_SYNC_RELAY_COMPONENT = "git-sync-relay"

# Expected sidecar-bearing components per DagDeployment stage (see the two fixtures).
SIDECAR_COMPONENTS_DAG_DEPLOY = STANDARD_SIDECAR_COMPONENTS | {DAG_SERVER_COMPONENT}
SIDECAR_COMPONENTS_GIT_SYNC = STANDARD_SIDECAR_COMPONENTS | {GIT_SYNC_RELAY_COMPONENT}

# The log-shipping sidecar Houston injects into each Airflow deployment pod. Must match
# global.logging.loggingSidecar.name in configs/enable-logging-sidecar-custom-config.yaml.
DEPLOYMENT_SIDECAR_CONTAINER_NAME = "sidecar-log-consumer"

# customConfig: true -> the sidecar's config comes from this fixed-name Secret, mounted
# through this volume.
SIDECAR_CONFIG_SECRET_NAME = "sidecar-config"
SIDECAR_CONFIG_VOLUME_NAME = "config-volume"

# A minimal, self-contained Vector config.
CUSTOM_VECTOR_CONFIG = f"""\
data_dir: /var/lib/vector
sources:
  file_logs:
    type: file
    include:
      - /var/log/{DEPLOYMENT_SIDECAR_CONTAINER_NAME}/*.log
sinks:
  console:
    type: console
    inputs:
      - file_logs
    encoding:
      codec: json
"""


@pytest.fixture(scope="module")
def _k8s_apps_v1_client_module() -> client.AppsV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def _k8s_core_v1_client_module() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def _houston_api_module():
    pod = get_pod_by_label_selector(NAMESPACE, "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={NAMESPACE}", kubeconfig=KUBECONFIG_UNIFIED)


@pytest.fixture(scope="module")
def _admin_token(_houston_api_module):
    return create_user(_houston_api_module, ADMIN_EMAIL, ADMIN_PASSWORD)


def _wait_for_release_namespace(apps_client, release_name: str, timeout: int = 120) -> str:
    """
    Poll for the namespace Commander created for this release and return it.
    """
    deadline = time.monotonic() + timeout
    label_selector = f"release={release_name}"
    while True:
        workloads = (
            apps_client.list_deployment_for_all_namespaces(label_selector=label_selector).items
            + apps_client.list_stateful_set_for_all_namespaces(label_selector=label_selector).items
        )
        namespaces = {w.metadata.namespace for w in workloads}
        if namespaces:
            # All of a release's workloads live in one namespace; take any.
            return next(iter(namespaces))
        if time.monotonic() > deadline:
            raise TimeoutError(f"No workloads for release {release_name!r} appeared within {timeout}s")
        time.sleep(3)


def _create_sidecar_config_secret(core_client, namespace: str) -> None:
    """Create (or replace) the fixed-name 'sidecar-config' Secret the injected sidecar
    mounts under customConfig: true. Houston references but never creates it, so without
    this the injected pods can't mount config-volume and never reach Running."""
    secret = client.V1Secret(
        metadata=client.V1ObjectMeta(name=SIDECAR_CONFIG_SECRET_NAME, namespace=namespace),
        string_data={"vector.yaml": CUSTOM_VECTOR_CONFIG},
    )
    try:
        core_client.create_namespaced_secret(namespace, secret)
    except client.exceptions.ApiException as exc:
        if exc.status != 409:  # already exists (e.g. a flaky rerun) -- overwrite it
            raise
        core_client.replace_namespaced_secret(SIDECAR_CONFIG_SECRET_NAME, namespace, secret)


@pytest.fixture(scope="module")
def deployment(_admin_token, _houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """Creates a real dag_deploy Airflow Deployment through Houston"""
    token = _admin_token
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

    release_name = created["releaseName"]
    namespace = _wait_for_release_namespace(_k8s_apps_v1_client_module, release_name)
    _create_sidecar_config_secret(_k8s_core_v1_client_module, namespace)

    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, release_name)
    return {"token": token, "id": created["id"], "release_name": release_name, "namespace": namespace}


@pytest.fixture(scope="module")
def git_sync_deployment(deployment, _houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """Switches the SAME deployment from dag_deploy to git_sync."""
    token = deployment["token"]
    before = snapshot_release_revisions(_k8s_apps_v1_client_module, deployment["release_name"])
    try:
        created = upsert_deployment(
            _houston_api_module,
            token,
            executor="CeleryExecutor",
            deployment_uuid=deployment["id"],
            dag_deployment_type="git_sync",
            repository_url=GIT_SYNC_REPOSITORY_URL,
            auth_type="HTTPS_NONE",
        )
    except HoustonError:
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    wait_for_release_ready(
        _k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"], previous_revisions=before
    )
    return {
        "token": token,
        "id": created["id"],
        "release_name": created["releaseName"],
        "namespace": deployment["namespace"],
    }


def _sidecar_pods(core_client, release_name: str) -> list:
    """The release's pods that actually carry the injected sidecar container. Scoped this
    way because Houston injects the sidecar only into log-producing Airflow components,
    not every pod in the release"""
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    return [p for p in pods if DEPLOYMENT_SIDECAR_CONTAINER_NAME in {c.name for c in p.spec.containers}]


def _pod_component(pod) -> str:
    """A pod's `component` label, or "" if unlabeled (so an unexpected unlabeled sidecar
    pod still surfaces in the canary diff rather than being silently dropped)."""
    return (pod.metadata.labels or {}).get("component") or ""


def _components_carrying_sidecar(core_client, release_name: str) -> set:
    """The set of `component` labels across the release's pods that carry the injected
    sidecar container -- the observed side of the canary assertion below."""
    return {_pod_component(p) for p in _sidecar_pods(core_client, release_name)}


def _assert_sidecar_components(core_client, release_name: str, expected: set) -> None:
    """Assert the EXACT set of sidecar-bearing components equals `expected`, with a diff on
    mismatch. Mirrors auth-sidecar's _assert_auth_proxy_components: a component losing the
    sidecar shows up as unexpectedly-missing, and one gaining it (or a runtime/toggle change
    that adds a component) shows up as unexpectedly-present -- either way a human re-confirms."""
    actual = _components_carrying_sidecar(core_client, release_name)
    assert actual == expected, (
        f"Set of components carrying the {DEPLOYMENT_SIDECAR_CONTAINER_NAME!r} sidecar changed for "
        f"release {release_name!r} -- re-confirm loggingSidecar wiring, then update the expected set "
        "only if the change is intended.\n"
        f"  expected:             {sorted(expected)}\n"
        f"  actual:               {sorted(actual)}\n"
        f"  unexpectedly present: {sorted(actual - expected)}\n"
        f"  unexpectedly missing: {sorted(expected - actual)}"
    )


def _pods_for_component(core_client, release_name: str, component: str) -> list:
    """The release's pods with the given `component` label (e.g. dag-server, git-sync-relay)."""
    return [
        p
        for p in core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
        if (p.metadata.labels or {}).get("component") == component
    ]


def _secret_mount_problems(pods) -> dict:
    """For each given pod, verify the sidecar mounts its config from the 'sidecar-config'
    Secret via 'config-volume' -- and NOT from a ConfigMap. Returns {pod_name: reason} for
    any pod that fails, empty if all pass. Shared by the whole-release and the
    per-component (dag-server / git-sync-relay) assertions."""
    problems = {}
    for pod in pods:
        volumes = {v.name: v for v in (pod.spec.volumes or [])}
        vol = volumes.get(SIDECAR_CONFIG_VOLUME_NAME)
        if vol is None:
            problems[pod.metadata.name] = f"no {SIDECAR_CONFIG_VOLUME_NAME!r} volume"
        elif vol.secret is None:
            # e.g. it fell back to a configMap -- the exact regression this guards against.
            problems[pod.metadata.name] = f"{SIDECAR_CONFIG_VOLUME_NAME!r} is not Secret-backed: {vol}"
        elif vol.secret.secret_name != SIDECAR_CONFIG_SECRET_NAME:
            problems[pod.metadata.name] = f"Secret is {vol.secret.secret_name!r}, expected {SIDECAR_CONFIG_SECRET_NAME!r}"
    return problems


def _assert_component_has_sidecar_and_secret(core_client, release_name: str, component: str) -> None:
    """A pod of `component` exists, carries the injected sidecar container, and mounts the
    customConfig Secret. Used for the dag-server (dag_deploy) and git-sync-relay (git_sync)
    consumers specifically -- each only exists in its DagDeployment type."""
    pods = _pods_for_component(core_client, release_name, component)
    assert pods, f"No {component!r} pod found for release {release_name!r}"

    without_container = [
        p.metadata.name for p in pods if DEPLOYMENT_SIDECAR_CONTAINER_NAME not in {c.name for c in p.spec.containers}
    ]
    assert not without_container, (
        f"{component!r} pods missing the {DEPLOYMENT_SIDECAR_CONTAINER_NAME!r} container: {without_container}"
    )

    problems = _secret_mount_problems(pods)
    assert not problems, (
        f"{component!r} pods not mounting the {SIDECAR_CONFIG_SECRET_NAME!r} Secret via {SIDECAR_CONFIG_VOLUME_NAME!r}: {problems}"
    )


def test_deployment_reaches_ready(deployment):
    assert deployment["release_name"]


def test_all_deployment_pods_have_sidecar_container(deployment, _k8s_core_v1_client_module):
    """The EXACT set of components carrying the injected sidecar equals the pinned
    dag_deploy set -- no more, no less.

    Pinned as a canary rather than "at least one" (see SIDECAR_COMPONENTS_DAG_DEPLOY): the
    sidecar is injected only into specific log-producing components, so this fails both when
    an expected component silently loses the sidecar AND when an unexpected component
    (pgbouncer, statsd, flower, a new component from a runtime bump) gains one."""
    _assert_sidecar_components(_k8s_core_v1_client_module, deployment["release_name"], SIDECAR_COMPONENTS_DAG_DEPLOY)


@pytest.mark.flaky(reruns=3, reruns_delay=10)
def test_sidecar_container_is_running_in_each_pod(deployment, _k8s_core_v1_client_module):
    """The injected sidecar is not just present in the pod spec but has actually reached
    the Running state in every pod that carries it.

    This is what proves the customConfig Secret mount works end to end: a missing or
    malformed 'sidecar-config' Secret leaves the container present in the spec but stuck
    Waiting (mount failure) or CrashLoopBackOff (bad config)."""
    sidecar_pods = _sidecar_pods(_k8s_core_v1_client_module, deployment["release_name"])
    assert sidecar_pods, f"No sidecar-carrying pods for release {deployment['release_name']!r}"

    not_running = {}
    for pod in sidecar_pods:
        statuses = {cs.name: cs for cs in (pod.status.container_statuses or [])}
        cs = statuses.get(DEPLOYMENT_SIDECAR_CONTAINER_NAME)
        if cs is None or cs.state is None or cs.state.running is None:
            not_running[pod.metadata.name] = "no container status" if cs is None else str(cs.state)

    assert not not_running, (
        f"Expected the {DEPLOYMENT_SIDECAR_CONTAINER_NAME!r} sidecar to be Running in every "
        f"carrying pod of Airflow deployment {deployment['release_name']!r}, but it was not in: {not_running}"
    )


def test_all_deployment_pods_mount_sidecar_secret(deployment, _k8s_core_v1_client_module):
    """Under customConfig: true, every sidecar-carrying pod mounts its config from the
    'sidecar-config' Secret (via the 'config-volume' volume) -- and NOT from a ConfigMap.

    This is the core customConfig assertion: it pins the exact source (a Secret, by the
    houston-api fixed name) rather than just "some config volume", so a regression that
    reverts to the default ConfigMap path fails here."""
    release_name = deployment["release_name"]
    sidecar_pods = _sidecar_pods(_k8s_core_v1_client_module, release_name)
    assert sidecar_pods, f"No sidecar-carrying pods for release {release_name!r}"

    problems = _secret_mount_problems(sidecar_pods)
    assert not problems, (
        f"Expected every sidecar pod of {release_name!r} to mount the {SIDECAR_CONFIG_SECRET_NAME!r} Secret "
        f"via {SIDECAR_CONFIG_VOLUME_NAME!r}, but: {problems}"
    )


def test_default_sidecar_configmap_not_created(deployment, _k8s_core_v1_client_module):
    """Under customConfig: true, the default per-release ConfigMap
    '<releaseName>-sidecar-config' (the customConfig: false path) must NOT exist.

    The negative counterpart to test_all_deployment_pods_mount_sidecar_secret: together
    they prove the config is sourced from the Secret and only the Secret."""
    release_name = deployment["release_name"]
    namespace = deployment["namespace"]
    default_configmap_name = f"{release_name}-sidecar-config"
    try:
        _k8s_core_v1_client_module.read_namespaced_config_map(default_configmap_name, namespace)
        raise AssertionError(
            f"Default ConfigMap {default_configmap_name!r} exists in {namespace!r}, but customConfig: true "
            f"should source the sidecar config from the {SIDECAR_CONFIG_SECRET_NAME!r} Secret instead"
        )
    except client.exceptions.ApiException as exc:
        assert exc.status == 404, f"Unexpected error checking for {default_configmap_name!r}: {exc}"


def test_dag_server_pod_has_sidecar_and_secret(deployment, _k8s_core_v1_client_module):
    """The dag-server pod (present only in the dag_deploy DagDeployment type) carries the
    injected logging sidecar and mounts the customConfig Secret.

    dag-server injects the sidecar through airflow-chart's own dag-server-statefulset.yaml
    (logging_sidecar_container_spec + loggingSidecar.VolumeMounts helpers), a separate path
    from the standard Airflow components -- so it needs its own assertion, not coverage by
    the whole-release checks above."""
    _assert_component_has_sidecar_and_secret(_k8s_core_v1_client_module, deployment["release_name"], DAG_SERVER_COMPONENT)


def test_git_sync_relay_pod_has_sidecar_and_secret(git_sync_deployment, _k8s_core_v1_client_module):
    """The git-sync-relay pod (present only after switching to the git_sync DagDeployment
    type) carries the injected logging sidecar and mounts the customConfig Secret.

    git-sync-relay injects the sidecar through airflow-chart's own
    git-sync-relay-deployment.yaml, gated purely on loggingSidecar.enabled (any fetch
    mode) -- the third and last consumer, and again a separate path from the standard
    Airflow components."""
    _assert_component_has_sidecar_and_secret(
        _k8s_core_v1_client_module, git_sync_deployment["release_name"], GIT_SYNC_RELAY_COMPONENT
    )


def test_git_sync_deployment_sidecar_components(git_sync_deployment, _k8s_core_v1_client_module):
    """The EXACT set of sidecar-bearing components after the git_sync switch equals the
    pinned git_sync set -- the canary counterpart to test_all_deployment_pods_have_sidecar_container
    for the git_sync stage.

    Differs from the dag_deploy set by exactly one member: git-sync-relay replaces
    dag-server. So this also catches an incomplete dag_deploy->git_sync transition -- a
    dag-server left behind shows up as unexpectedly present, a missing relay as unexpectedly
    missing."""
    _assert_sidecar_components(_k8s_core_v1_client_module, git_sync_deployment["release_name"], SIDECAR_COMPONENTS_GIT_SYNC)
