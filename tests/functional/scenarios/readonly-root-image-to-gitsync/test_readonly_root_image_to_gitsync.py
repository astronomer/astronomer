"""readonly-root-image-to-gitsync: creates a real Airflow Deployment (CeleryExecutor, dagDeploymentType
image), then disables Houston's default readOnlyRootFilesystem via a live platform helm
upgrade (configs/disable-airflow-readonly-root.yaml, tests/utils/helm.py) and forces the
already-existing deployment to pick up the change with a throwaway upsertDeployment call
(upgradeDeployments is left disabled -- see that config file for why its own automatic hook
wouldn't actually propagate a config-only change like this one). Finally switches the same
deployment's DagDeploymentType Image -> GitSync via upsertDeployment and
re-asserts, to prove the override survives a DagDeploymentType switch too -- not just a forced
redeploy with the deployment's mechanism left untouched.

One of four readonly-root-*-to-* scenarios that are identical except for which
DagDeploymentType they start and end on; the shared assertion lives in
tests/utils/readonly_root.py.
"""

import pytest
import testinfra
from kubernetes import client, config

from tests.utils.helm import GIT_ROOT_DIR, upgrade_platform_release
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
from tests.utils.readonly_root import GIT_SYNC_REPOSITORY_URL, assert_no_readonly_root_containers

NAMESPACE = "astronomer"
SCENARIO_LABEL = "readonly-root-image-to-gitsync"
ADMIN_EMAIL = f"{SCENARIO_LABEL}-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = SCENARIO_LABEL
DEPLOYMENT_LABEL = SCENARIO_LABEL

FROM_DAG_DEPLOYMENT_TYPE = "image"
TO_DAG_DEPLOYMENT_TYPE = "git_sync"

DISABLE_READONLY_ROOT_VALUES = str(GIT_ROOT_DIR / "configs" / "disable-airflow-readonly-root.yaml")

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
    """Resolve the current houston pod fresh -- deliberately not cached in a fixture. The live
    platform helm upgrade in test_forced_redeploy_disables_readonly_root changes houston's own
    ConfigMap, which restarts houston (and houston-worker) via their checksum/houston-config
    pod-template annotation -- so a pod name resolved before that upgrade is deleted by the time
    a later test tries to exec into it. Re-resolving on every call costs one cheap pod-list call
    and is correct across any number of restarts, not just the one this file causes.
    """
    pod = get_pod_by_label_selector(NAMESPACE, "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={NAMESPACE}", kubeconfig=KUBECONFIG_UNIFIED)


@pytest.fixture(scope="module")
def _k8s_apps_v1_client_module() -> client.AppsV1Api:
    """Module-scoped so the deployment fixture below (also module-scoped, to avoid paying for a
    fresh Airflow Deployment per test) can depend on it -- conftest.py's own k8s_apps_v1_client
    is function-scoped and can't be used by a module-scoped fixture. Unlike the houston pod
    above, this client object stays valid across houston's own restarts: it just points at a
    kubeconfig, not any specific pod."""
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
    return {"token": token, "id": created["id"], "release_name": created["releaseName"]}


def test_deployment_reaches_ready(deployment):
    """The deployment fixture already waits for readiness -- this test asserts that contract
    explicitly, so a fixture-setup failure surfaces as a named test result rather than only as a
    collection error."""
    assert deployment["release_name"]


def test_forced_redeploy_disables_readonly_root(deployment, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """Upgrades the platform release to disable readOnlyRootFilesystem, then forces the
    already-existing deployment to pick it up with a throwaway upsertDeployment call -- nothing
    about the deployment's own executor/dagDeployment changes, only a new environment variable,
    which is enough to make Commander re-render and re-apply its Helm values. That re-render
    freshly fetches the platform's current config server-side (upsertDeployment's own resolver
    behavior), which is exactly what upgradeDeployments' own automatic hook does NOT do -- see
    upsert_deployment's docstring and configs/disable-airflow-readonly-root.yaml.

    Snapshots the deployment's workload generations first and passes them to
    wait_for_release_ready: Commander applies the change asynchronously, so without the baseline
    the wait would return immediately against the still-ready pre-upgrade pods.
    """
    before = snapshot_release_revisions(_k8s_apps_v1_client_module, deployment["release_name"])
    upgrade_platform_release(KUBECONFIG_UNIFIED, DISABLE_READONLY_ROOT_VALUES)
    try:
        upsert_deployment(
            _houston_api(),
            deployment["token"],
            executor="CeleryExecutor",
            deployment_uuid=deployment["id"],
            environment_variables=[{"key": FORCE_REDEPLOY_ENV_VAR_KEY, "value": "1"}],
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
    """Switches the same deployment Image -> GitSync via upsertDeployment on the
    same deployment_uuid, after readOnlyRootFilesystem has already been disabled platform-wide
    (relies on running after test_forced_redeploy_disables_readonly_root, the same implicit
    within-module ordering deployment-lifecycle.py and auth-sidecar's own executor/
    DagDeploymentType-switch tests already rely on), and re-asserts no container on the new
    topology re-enables it. Resolves the houston pod fresh (_houston_api()) rather than reusing
    one from earlier in the module: the previous test's platform upgrade may have restarted it.
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
