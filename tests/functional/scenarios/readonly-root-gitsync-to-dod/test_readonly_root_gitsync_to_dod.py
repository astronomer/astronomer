"""readonly-root-gitsync-to-dod: creates a real Airflow Deployment (CeleryExecutor, dagDeploymentType
git_sync), then disables Houston's default readOnlyRootFilesystem for the cluster it's on
via updateCluster's deploymentsConfigOverride, and forces the already-existing deployment to
pick up the change with a throwaway upsertDeployment call. Finally switches the same
deployment's DagDeploymentType GitSync -> DagOnlyDeployment (dag_deploy) via upsertDeployment and
re-asserts, to prove the override survives a DagDeploymentType switch too -- not just a forced
redeploy with the deployment's mechanism left untouched.

Deliberately NOT a platform helm upgrade of astronomer's own houston.config.deployments.*: a
plain `helm upgrade` only changes the live platform config, which houston-api only ever reads
into a Cluster's OWN stored config.deployments once, at that cluster's creation
(populate-default-cluster snapshots it on houston's first-ever startup and never refreshes it) --
so it's invisible to any cluster (like the one this scenario's deployment already runs on)
that existed before the upgrade ran. update_cluster's deploymentsConfigOverride is what actually
reaches an already-registered cluster's deployments. See update_cluster's and
upsert_deployment's docstrings in tests/utils/houston_graphql.py for the full mechanics.

One of four readonly-root-*-to-* scenarios that are identical except for which
DagDeploymentType they start and end on; the shared assertion lives in
tests/utils/readonly_root.py.
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
    snapshot_release_revisions,
    update_cluster,
    upsert_deployment,
    wait_for_release_ready,
)
from tests.utils.k8s import KUBECONFIG_UNIFIED, get_pod_by_label_selector
from tests.utils.readonly_root import GIT_SYNC_REPOSITORY_URL, assert_no_readonly_root_containers

NAMESPACE = "astronomer"
SCENARIO_LABEL = "readonly-root-gitsync-to-dod"
ADMIN_EMAIL = f"{SCENARIO_LABEL}-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = SCENARIO_LABEL
DEPLOYMENT_LABEL = SCENARIO_LABEL

# PINF-1049: commander's first-ever JWKS fetch (cache cold) can race Houston's own K8s
# Ready-gate and get a literal connection refusal, surfacing as this exact HoustonError
# message from upsertDeployment -- see auth-sidecar's own test file for the full mechanics.
# @pytest.mark.flaky(only_rerun=[...]) below re-runs the whole `deployment` fixture (including
# its create_user/create_workspace calls) on this exact message -- not a fix for a bug in this
# repo.
JWKS_COLD_START_ERROR = "13 INTERNAL: failed to validate token"

FROM_DAG_DEPLOYMENT_TYPE = "git_sync"
TO_DAG_DEPLOYMENT_TYPE = "dag_deploy"

# Merged into the cluster's config.deployments via update_cluster -- see that function's
# docstring for why this, and not a platform helm upgrade, is what actually disables
# readOnlyRootFilesystem for deployments already on this cluster.
DISABLE_READONLY_ROOT_OVERRIDE = {"securityContext": {"container": {"readOnlyRootFilesystem": False}}}

# A throwaway env var, added via upsertDeployment purely to force Commander to re-render and
# re-apply this deployment's Helm values -- see upsert_deployment's docstring for why this is
# necessary instead of relying on upgradeDeployments' own automatic hook.
FORCE_REDEPLOY_ENV_VAR_KEY = "READONLY_ROOT_TEST_FORCE_REDEPLOY"


def _dag_deployment_kwargs(dag_deployment_type: str) -> dict:
    """git_sync needs a repository_url; image/dag_deploy need neither.

    No auth_type: the houston-api version this chart pins (v2.0.37) predates authType/HTTPS+PAT
    entirely (git_sync there is SSH-key or public-HTTPS only), and GIT_SYNC_REPOSITORY_URL is a
    public repo needing no credentials of any kind -- see upsert_deployment's docstring for what
    sending authType against this schema actually does (a GraphQL error, not a local validation
    failure).
    """
    if dag_deployment_type == "git_sync":
        return {"repository_url": GIT_SYNC_REPOSITORY_URL}
    return {}


def _houston_api():
    """Resolve the current houston pod fresh -- deliberately not cached in a fixture, so a test
    file that ever needs to survive a houston restart (a platform helm upgrade, a config change
    that flips houston's own checksum/houston-config pod-template annotation) can't be holding a
    stale, since-deleted pod name. Costs one cheap pod-list call per invocation.
    """
    pod = get_pod_by_label_selector(NAMESPACE, "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={NAMESPACE}", kubeconfig=KUBECONFIG_UNIFIED)


@pytest.fixture(scope="module")
def _k8s_apps_v1_client_module() -> client.AppsV1Api:
    """Module-scoped so the deployment fixture below (also module-scoped, to avoid paying for a
    fresh Airflow Deployment per test) can depend on it -- conftest.py's own k8s_apps_v1_client
    is function-scoped and can't be used by a module-scoped fixture."""
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def _k8s_core_v1_client_module() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def deployment(_k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """Bootstraps a fresh admin user and workspace, creates an Airflow Deployment with
    FROM_DAG_DEPLOYMENT_TYPE through Houston's GraphQL API, and waits for it to reach full
    readiness. Module-scoped: every test in this file shares the one deployment."""
    houston_api = _houston_api()
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
            dag_deployment_type=FROM_DAG_DEPLOYMENT_TYPE,
            **_dag_deployment_kwargs(FROM_DAG_DEPLOYMENT_TYPE),
        )
    except HoustonError:
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"])
    return {"token": token, "id": created["id"], "release_name": created["releaseName"], "cluster_id": cluster_id}


@pytest.mark.flaky(reruns=5, reruns_delay=5, only_rerun=[JWKS_COLD_START_ERROR])
def test_deployment_reaches_ready(deployment):
    """The deployment fixture already waits for readiness -- this test asserts that contract
    explicitly, so a fixture-setup failure surfaces as a named test result rather than only as a
    collection error."""
    assert deployment["release_name"]


def test_forced_redeploy_disables_readonly_root(deployment, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """Disables readOnlyRootFilesystem on the deployment's cluster via update_cluster, then
    forces the already-existing deployment to pick it up with an upsertDeployment call carrying
    a throwaway environment variable. That alone is enough to make Commander re-render most
    components -- but NOT webserver's own container: confirmed empirically (2026-09-04 CI) that
    webserver's rendered securityContext only gets recomputed when the mutation call also
    includes a dagDeployment.type argument, even when it's the deployment's own current,
    unchanged type -- omitting dagDeployment (as a bare env-var-only update would) leaves
    webserver's Helm values stale relative to whatever config was in effect at the last call
    that DID include it. So this re-asserts FROM_DAG_DEPLOYMENT_TYPE explicitly rather than
    omitting it, to force the full render path for every component, not just most of them.

    Snapshots the deployment's workload generations first and passes them to
    wait_for_release_ready: Commander applies the change asynchronously, so without the baseline
    the wait would return immediately against the still-ready pre-change pods.
    """
    houston_api = _houston_api()
    update_cluster(
        houston_api,
        deployment["token"],
        cluster_id=deployment["cluster_id"],
        deployments_config_override=DISABLE_READONLY_ROOT_OVERRIDE,
    )
    before = snapshot_release_revisions(_k8s_apps_v1_client_module, deployment["release_name"])
    try:
        upsert_deployment(
            houston_api,
            deployment["token"],
            executor="CeleryExecutor",
            deployment_uuid=deployment["id"],
            dag_deployment_type=FROM_DAG_DEPLOYMENT_TYPE,
            environment_variables=[{"key": FORCE_REDEPLOY_ENV_VAR_KEY, "value": "1"}],
            **_dag_deployment_kwargs(FROM_DAG_DEPLOYMENT_TYPE),
        )
    except HoustonError:
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    wait_for_release_ready(
        _k8s_apps_v1_client_module, _k8s_core_v1_client_module, deployment["release_name"], previous_revisions=before
    )
    assert_no_readonly_root_containers(_k8s_core_v1_client_module, deployment["release_name"])


def test_deployment_survives_dag_deployment_type_switch(deployment, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """Switches the same deployment GitSync -> DagOnlyDeployment (dag_deploy) via upsertDeployment on the
    same deployment_uuid, after readOnlyRootFilesystem has already been disabled on this
    deployment's cluster (relies on running after test_forced_redeploy_disables_readonly_root,
    the same implicit within-module ordering deployment-lifecycle.py and auth-sidecar's own
    executor/DagDeploymentType-switch tests already rely on), and re-asserts no container on the
    new topology re-enables it. Resolves the houston pod fresh (_houston_api()) rather than
    reusing one from earlier in the module, in case anything upstream ever restarts it.
    """
    token = deployment["token"]
    before = snapshot_release_revisions(_k8s_apps_v1_client_module, deployment["release_name"])
    try:
        created = upsert_deployment(
            _houston_api(),
            token,
            executor="CeleryExecutor",
            deployment_uuid=deployment["id"],
            dag_deployment_type=TO_DAG_DEPLOYMENT_TYPE,
            **_dag_deployment_kwargs(TO_DAG_DEPLOYMENT_TYPE),
        )
    except HoustonError:
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    wait_for_release_ready(
        _k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"], previous_revisions=before
    )
    assert_no_readonly_root_containers(_k8s_core_v1_client_module, created["releaseName"])
