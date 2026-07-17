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

Mutation shapes and the createUser-then-createWorkspace bootstrap sequence
(tests/utils/houston_graphql.py) are ported from software-upgrade-automation's
bin/configure-k3d-for-tests.py and bin/create-git-sync-deployment.py (QA's own k3d
CP/DP test tooling), adapted for the unified topology: no registerCluster call is
needed here, because houston-api's populate-default-cluster script already creates a
default Cluster row on startup whenever plane.mode is unified.
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

NAMESPACE = "astronomer"
ADMIN_EMAIL = "pinf-1035-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "pinf-1035"
DEPLOYMENT_LABEL = "pinf-1035-lifecycle"


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
        )
    except HoustonError:
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"])
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
