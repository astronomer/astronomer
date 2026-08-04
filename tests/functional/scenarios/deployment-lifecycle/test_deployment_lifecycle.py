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

PINF-1109 rides along on the same one deployment: it is created as a git_sync relay
deployment (no global.privateCaCerts in this scenario), which lets test_relay_has_no_private_ca_wiring
assert the feature-OFF case -- the relay carries no private-CA wiring unless the CA is
configured -- as a live counterpart to the git-sync-private-ca scenario's positive tests.

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
    Houston's GraphQL API, and waits for it to reach full readiness. Module-scoped: every
    test in this file shares the one deployment, since creating it is the expensive part;
    the executor-switch test needs an already-ready deployment to switch, and TC-CA-05a
    inspects the same deployment's git-sync-relay pod.

    Created as a git_sync relay deployment (HTTPS_NONE, public apc-test-dags-public) rather
    than as a plain image deployment: a git_sync deployment must be CREATED as git_sync to
    get a relay. Transitioning an existing deployment to git_sync via a later upsertDeployment
    does NOT reliably provision the relay -- CI showed an image->git_sync switch left the
    deployment with no relay pod at all, and auth-sidecar's dag_deploy->git_sync switch leaves
    the old dag-downloader sidecar in place -- so the git-sync-private-ca scenario (which works)
    also creates fresh as git_sync. Creating it here keeps the whole scenario on one deployment:
    the executor switch (PINF-1035) is orthogonal to the git-sync relay and leaves it intact,
    and readiness requires the relay to actually clone the public repo (its git-daemon probes
    check a post-clone marker), so it doubles as the e2e proof the relay's default no-CA path
    works. TC-CA-05a then asserts that relay carries no private-CA wiring.

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
            dag_deployment_type="git_sync",
            repository_url=GIT_SYNC_REPOSITORY_URL,
            auth_type="HTTPS_NONE",
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


def _relay_pod(core_client, release_name):
    """The git-sync-relay pod for a release. Match by pod NAME (<release>-git-sync-relay-*), not a
    git-sync *container* name: the Airflow component pods each carry a git-sync sidecar, so a
    container-name match would also hit them. Read the namespace off the pod -- the Airflow
    Deployment namespace is astronomer-<release>, not the release name."""
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    relay = [p for p in pods if "git-sync-relay" in p.metadata.name]
    assert relay, f"No git-sync-relay pod for release {release_name!r} (pods: {[p.metadata.name for p in pods]})"
    return relay[0]


def test_relay_has_no_private_ca_wiring(deployment, _k8s_core_v1_client_module):
    """TC-CA-05a (PINF-1109): with no global.privateCaCerts configured, the git-sync-relay pod
    carries NONE of the private-CA wiring the git-sync-private-ca scenario asserts is present when
    it IS set -- no etc-ssl-certs-copier initContainer, no private-ca-* volume, and no
    UPDATE_CA_CERTS on the git-sync container. The feature-OFF counterpart: it proves that wiring is
    genuinely driven by global.privateCaCerts and not always emitted, so a regression that quietly
    always-mounted the CA would still pass the positive test over there but fail here. (The relay
    reaching ready against a public HTTPS repo with no CA is the e2e functional half -- the relay
    clones normally with no private-CA trust configured.)"""
    pod = _relay_pod(_k8s_core_v1_client_module, deployment["release_name"])
    init_names = [c.name for c in (pod.spec.init_containers or [])]
    assert "etc-ssl-certs-copier" not in init_names, f"Unexpected CA-copier initContainer with no privateCaCerts: {init_names}"
    volume_names = [v.name for v in pod.spec.volumes]
    assert not any(v.startswith("private-ca-") for v in volume_names), f"Unexpected private-ca-* volume: {volume_names}"
    git_sync = next(c for c in pod.spec.containers if "git-sync" in c.name)
    env = {e.name: e.value for e in (git_sync.env or [])}
    assert env.get("UPDATE_CA_CERTS") != "true", f"Unexpected UPDATE_CA_CERTS=true with no privateCaCerts: {env}"
