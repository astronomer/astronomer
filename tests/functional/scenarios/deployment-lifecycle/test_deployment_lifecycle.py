"""PINF-1035: creates a real Airflow Deployment through Houston's GraphQL API, then
switches its executor (CeleryExecutor -> KubernetesExecutor) -- the specific
regression class PINF-1033 was caught in, via getExecutorConfig/
replaceWithExecutorSpecificResources. PINF-1031's auth-sidecar scenario also creates a
real Airflow Deployment and re-invokes upsertDeployment, but to switch dagDeploymentType
(dag_deploy -> git_sync) instead, via gitSyncTransition -- a different upsertDeployment
argument and a different houston-api code path than the executor switch here.

Uses the GraphQL API deliberately, not Commander's gRPC interface directly (which
Commander's own component tests already exercise): GraphQL is the core API for the APC
app -- the UI and astro-cli go through it -- so testing through it exercises the actual
path a real customer takes (houston-api -> NATS JetStream -> houston-worker -> Commander
-> Helm), not just Commander's Helm-templating logic in isolation.

Doesn't reproduce PINF-1033 itself -- that bug was an OpenShift/ARO-SCC UID collision,
invisible to this kind-based CI by construction (see PINF-716/MV for that gap). This
catches Helm-values-assembly and upgrade-path regressions that break on any cluster,
generic or OpenShift alike.

Mutation shapes and the createUser-then-createWorkspace bootstrap sequence
(tests/utils/houston_graphql.py) are ported from software-upgrade-automation's
bin/configure-k3d-for-tests.py and bin/create-git-sync-deployment.py (QA's own k3d
CP/DP test tooling), adapted for the unified topology: no registerCluster call is
needed here, because houston-api's populate-default-cluster script already creates a
default Cluster row on startup whenever plane.mode is unified.
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
    upsert_deployment,
    wait_for_release_ready,
)
from tests.utils.k8s import KUBECONFIG_UNIFIED, get_pod_by_label_selector

NAMESPACE = "astronomer"
ADMIN_EMAIL = "pinf-1035-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "pinf-1035"
DEPLOYMENT_LABEL = "pinf-1035-lifecycle"
# TC-CA-05a: a public, no-auth repo so the relay clones with no credentials and no private CA
# in CI (same choice as auth-sidecar). Readiness requires a real clone of it.
GIT_SYNC_REPOSITORY_URL = "https://github.com/astronomer/apc-test-dags-public"


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
    Bootstraps a fresh admin user and workspace, creates an Airflow Deployment through
    Houston's GraphQL API, and waits for it to reach full readiness. Module-scoped: both
    tests in this file share the one deployment, since creating it is the expensive part
    and the switch test needs an already-ready deployment to switch.

    Prints a timestamped line before/after each step: the failures seen so far
    (PINF-1068's pgbouncer crash-loop, PINF-1049's JWKS race) are intermittent, and
    without this the only visibility into this setup phase was wait_for_release_ready's
    own polling -- nothing showed whether create_user/create_workspace/get_cluster_id/
    upsert_deployment itself was slow, hung, or where a HoustonError actually came from.
    """
    start = time.monotonic()

    def _log(step: str) -> None:
        print(f"[deployment fixture] {step} ({time.monotonic() - start:.1f}s elapsed)")

    _log("creating admin user")
    token = create_user(_houston_api_module, ADMIN_EMAIL, ADMIN_PASSWORD)
    _log("creating workspace")
    workspace_id = create_workspace(_houston_api_module, token, WORKSPACE_LABEL)
    _log("looking up default cluster id")
    cluster_id = get_cluster_id(_houston_api_module, token)
    _log("calling upsertDeployment")
    try:
        created = upsert_deployment(
            _houston_api_module,
            token,
            executor="CeleryExecutor",
            label=DEPLOYMENT_LABEL,
            workspace_id=workspace_id,
            cluster_id=cluster_id,
        )
    except HoustonError:
        _log("upsertDeployment raised a HoustonError, dumping houston/commander logs")
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    _log(f"upsertDeployment returned releaseName={created['releaseName']!r}, waiting for readiness")
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"])
    _log("release is ready")
    return {"token": token, "id": created["id"], "release_name": created["releaseName"]}


def test_deployment_reaches_ready(deployment):
    """The deployment fixture already waits for readiness -- this test asserts that
    contract explicitly, so a fixture-setup failure surfaces as a named test result
    rather than only as a collection error."""
    assert deployment["release_name"]


def test_deployment_survives_executor_switch(deployment, houston_api, k8s_apps_v1_client, k8s_core_v1_client):
    """
    Exercises the failure class PINF-1033 was caught in: an Airflow Deployment upgrade
    that changes its executor. Re-invokes upsertDeployment on the same deployment_uuid,
    the same mutation Commander's own upgrade path uses.
    """
    upsert_deployment(
        houston_api,
        deployment["token"],
        executor="KubernetesExecutor",
        deployment_uuid=deployment["id"],
    )
    wait_for_release_ready(k8s_apps_v1_client, k8s_core_v1_client, deployment["release_name"])


@pytest.fixture(scope="module")
def git_sync_deployment(deployment, _houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """Switches the SAME deployment to a git_sync relay (dagDeployment.type: git_sync, HTTPS_NONE,
    pointed at the public apc-test-dags-public repo), reusing the one deployment rather than standing
    up a second -- two concurrent full Airflow Deployments exhaust even a 2xlarge CI node (see
    auth-sidecar / PINF-1080), so only one deployment's pods ever exist. This scenario sets no
    global.privateCaCerts, so the resulting relay gets no private-CA wiring: the feature-OFF case
    for TC-CA-05a. Readiness requires a real clone of the public repo, which proves the relay's
    default (no-CA) path works end-to-end.

    Passes executor="KubernetesExecutor" -- the executor the deployment is already in after
    test_deployment_survives_executor_switch -- so this is a pure dagDeploymentType switch with no
    executor change (mirroring auth-sidecar's git_sync fixture, which likewise doesn't combine the
    two). KubernetesExecutor also keeps no persistent worker pods at idle, holding the footprint down.
    """
    token = deployment["token"]
    try:
        created = upsert_deployment(
            _houston_api_module,
            token,
            executor="KubernetesExecutor",
            deployment_uuid=deployment["id"],
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


def _relay_pod(core_client, release_name):
    """The git-sync-relay pod for a release. Match by pod NAME (<release>-git-sync-relay-*), not a
    git-sync *container* name: the Airflow component pods each carry a git-sync sidecar, so a
    container-name match would also hit them. Read the namespace off the pod -- the Airflow
    Deployment namespace is astronomer-<release>, not the release name."""
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    relay = [p for p in pods if "git-sync-relay" in p.metadata.name]
    assert relay, f"No git-sync-relay pod for release {release_name!r} (pods: {[p.metadata.name for p in pods]})"
    return relay[0]


def test_relay_has_no_private_ca_wiring(git_sync_deployment, _k8s_core_v1_client_module):
    """TC-CA-05a (PINF-1109): with no global.privateCaCerts configured, the git-sync-relay pod
    carries NONE of the private-CA wiring the git-sync-private-ca scenario asserts is present when
    it IS set -- no etc-ssl-certs-copier initContainer, no private-ca-* volume, and no
    UPDATE_CA_CERTS on the git-sync container. The feature-OFF counterpart: it proves that wiring is
    genuinely driven by global.privateCaCerts and not always emitted, so a regression that quietly
    always-mounted the CA would still pass the positive test over there but fail here. (The relay
    reaching ready against a public HTTPS repo with no CA is the e2e functional half -- the relay
    clones normally with no private-CA trust configured.)"""
    pod = _relay_pod(_k8s_core_v1_client_module, git_sync_deployment["release_name"])
    init_names = [c.name for c in (pod.spec.init_containers or [])]
    assert "etc-ssl-certs-copier" not in init_names, f"Unexpected CA-copier initContainer with no privateCaCerts: {init_names}"
    volume_names = [v.name for v in pod.spec.volumes]
    assert not any(v.startswith("private-ca-") for v in volume_names), f"Unexpected private-ca-* volume: {volume_names}"
    git_sync = next(c for c in pod.spec.containers if "git-sync" in c.name)
    env = {e.name: e.value for e in (git_sync.env or [])}
    assert env.get("UPDATE_CA_CERTS") != "true", f"Unexpected UPDATE_CA_CERTS=true with no privateCaCerts: {env}"
