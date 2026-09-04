"""readonly-root-gitsync-to-dod: creates a real Airflow Deployment (CeleryExecutor, dagDeploymentType
git_sync), then disables Houston's default readOnlyRootFilesystem via a live platform helm
upgrade (configs/disable-airflow-readonly-root.yaml, tests/utils/helm.py) with upgradeDeployments
enabled, and confirms the already-existing deployment picks up the change on its own -- the
houston-upgrade-deployments-job pre-upgrade hook rolling it forward, with no per-deployment
upsertDeployment needed for the security-context change itself. Finally switches the same
deployment's DagDeploymentType GitSync -> DagOnlyDeployment (dag_deploy) via upsertDeployment and
re-asserts, to prove the override survives a DagDeploymentType switch too -- not just a plain
platform upgrade with the deployment's mechanism left untouched.

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
SCENARIO_LABEL = "readonly-root-gitsync-to-dod"
ADMIN_EMAIL = f"{SCENARIO_LABEL}-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = SCENARIO_LABEL
DEPLOYMENT_LABEL = SCENARIO_LABEL

FROM_DAG_DEPLOYMENT_TYPE = "git_sync"
TO_DAG_DEPLOYMENT_TYPE = "dag_deploy"

DISABLE_READONLY_ROOT_VALUES = str(GIT_ROOT_DIR / "configs" / "disable-airflow-readonly-root.yaml")


def _dag_deployment_kwargs(dag_deployment_type: str) -> dict:
    """git_sync needs a repository_url + auth_type; image/dag_deploy need neither."""
    if dag_deployment_type == "git_sync":
        return {"repository_url": GIT_SYNC_REPOSITORY_URL, "auth_type": "HTTPS_NONE"}
    return {}


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
def _houston_api_module():
    """Module-scoped counterpart to conftest.py's houston_api fixture, for the same reason as
    _k8s_apps_v1_client_module above."""
    pod = get_pod_by_label_selector(NAMESPACE, "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={NAMESPACE}", kubeconfig=KUBECONFIG_UNIFIED)


@pytest.fixture(scope="module")
def deployment(_houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """Bootstraps a fresh admin user and workspace, creates an Airflow Deployment with
    FROM_DAG_DEPLOYMENT_TYPE through Houston's GraphQL API, and waits for it to reach full
    readiness. Module-scoped: every test in this file shares the one deployment."""
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


def test_disabling_readonly_root_reaches_deployment_without_a_switch(
    deployment, _k8s_apps_v1_client_module, _k8s_core_v1_client_module
):
    """Upgrades the platform release to disable readOnlyRootFilesystem (with upgradeDeployments
    enabled) and confirms the already-existing deployment rolls forward on its own, before any
    DagDeploymentType switch happens -- isolating the upgradeDeployments mechanism itself from
    the switch tested next. Snapshots the deployment's workload generations first and passes
    them to wait_for_release_ready: the upgrade-deployments hook Job reconciles existing
    deployments via Commander asynchronously, so without the baseline the wait would return
    immediately against the still-ready pre-upgrade pods.
    """
    before = snapshot_release_revisions(_k8s_apps_v1_client_module, deployment["release_name"])
    upgrade_platform_release(KUBECONFIG_UNIFIED, DISABLE_READONLY_ROOT_VALUES)
    wait_for_release_ready(
        _k8s_apps_v1_client_module, _k8s_core_v1_client_module, deployment["release_name"], previous_revisions=before
    )
    assert_no_readonly_root_containers(_k8s_core_v1_client_module, deployment["release_name"])


def test_deployment_survives_dag_deployment_type_switch(
    deployment, _houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module
):
    """Switches the same deployment GitSync -> DagOnlyDeployment (dag_deploy) via upsertDeployment on the
    same deployment_uuid, after readOnlyRootFilesystem has already been disabled platform-wide
    (relies on running after test_disabling_readonly_root_reaches_deployment_without_a_switch,
    the same implicit within-module ordering deployment-lifecycle.py and auth-sidecar's own
    executor/DagDeploymentType-switch tests already rely on), and re-asserts no container on the
    new topology re-enables it.
    """
    token = deployment["token"]
    before = snapshot_release_revisions(_k8s_apps_v1_client_module, deployment["release_name"])
    try:
        created = upsert_deployment(
            _houston_api_module,
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
