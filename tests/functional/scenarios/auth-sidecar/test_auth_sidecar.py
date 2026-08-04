"""PINF-1031: catches the class of regression in PINF-1033 (a PSS-Restricted hardening
change broke global.authSidecar, not caught until QA). See test_profile.yaml for why
this scenario combines authSidecar with a PSS-Restricted-enforcing namespace rather
than testing them separately.

test_grafana_* covers the platform-namespace tier (astronomer chart: grafana,
alertmanager, prometheus). test_deployment_* and test_git_sync_deployment_* cover
the OTHER two authSidecar implementations that live in Airflow-Deployment-namespace
territory and were previously untestable here at all -- no scenario created a real
Airflow Deployment before PINF-1035 built the mechanism this reuses: houston-api's
server-side extraContainers() injection onto the deployment's own pods (via
dagDeployment.type: dag_deploy, which also turns on dag-server's own auth-sidecar
consumer -- see dag-server-auth-sidecar-configmap.yaml's `and .Values.dagDeploy.enabled
.Values.authSidecar.enabled` gate), and airflow-chart's git-sync-relay (via
dagDeployment.type: git_sync, authType: HTTPS_NONE, pointed at
astronomer/apc-test-dags-public -- a small public no-auth fixture repo, chosen
specifically so this doesn't need real git credentials in CI). All three
authSidecar implementations are now exercised here.

One deployment, switched from dag_deploy to git_sync via upsertDeployment on the same
deployment_uuid -- not two independent deployments. Two reasons: (1) it's a strictly
better test, since it also exercises DagDeploymentType-switching itself (mirroring
test_deployment_lifecycle.py's executor-switch pattern), a real capability nothing else
covers; (2) two full concurrent Airflow Deployments (each ~9 components) plus the
platform chart exhausted the CI node's CPU (FailedScheduling: Insufficient cpu on every
pod of the second deployment) once PINF-1049's commander-side JWKS fix stopped masking
it by failing earlier. Switching type on one deployment means only one deployment's
pods ever exist at a time.
"""

import re

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
from tests.utils.k8s import KUBECONFIG_UNIFIED, find_psa_rejection_events, get_pod_by_label_selector

# PINF-1049: commander's first-ever JWKS fetch (cache cold) can race Houston's own K8s
# Ready-gate and get a literal connection refusal, surfacing as this exact HoustonError
# message from upsertDeployment. commander PR #560 (ap-commander >= 2.1.11) added its
# own retry-with-backoff for this, but that window (~750ms) assumes the race resolves
# "within a few seconds" -- confirmed via a real CI recurrence on 2026-07-27 (commander
# 2.1.12) that it sometimes doesn't. @pytest.mark.flaky(only_rerun=[...]) below re-runs
# only on this exact message, re-invoking the whole `deployment`/`git_sync_deployment`
# fixture (including its create_workspace call, so a retry leaves a harmless orphaned
# extra workspace behind in this ephemeral cluster) -- not a fix for a bug in this repo.
JWKS_COLD_START_ERROR = "13 INTERNAL: failed to validate token"

GRAFANA_DEPLOYMENT_NAME = "astronomer-grafana"
NAMESPACE = "astronomer"
ADMIN_EMAIL = "pinf-1031-auth-sidecar-test@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "pinf-1031-auth-sidecar"
DEPLOYMENT_LABEL = "pinf-1031-auth-sidecar"
GIT_SYNC_REPOSITORY_URL = "https://github.com/astronomer/apc-test-dags-public"

# The EXACT set of pods (by component) expected to carry an auth-proxy sidecar in each stage.
# Pinned deliberately as a canary rather than asserting "at least one": authSidecar is implemented
# several times across repos, and the PINF-1033 regression this scenario exists for was a consumer
# silently LOSING its sidecar under a PSS-Restricted change -- which an at-least-one check sails
# right past. Asserting the whole set makes a consumer gaining OR losing the sidecar, or a runtime
# swap of the web component (webserver <-> api-server), fail loudly for a human to re-confirm.
# Each stage has two: the houston-injected web component (webserver on the current runtime) and the
# chart-injected stage consumer (dag-server for dag_deploy, git-sync-relay for git_sync).
AUTH_PROXY_COMPONENTS_DAG_DEPLOY = {"webserver", "dag-server"}
AUTH_PROXY_COMPONENTS_GIT_SYNC = {"webserver", "git-sync-relay"}


def test_grafana_deployment_reaches_ready(k8s_apps_v1_client):
    """
    A pod Pod Security Admission rejects is never created -- it never becomes an
    unhealthy Pod object, it surfaces as a FailedCreate event on the Deployment's
    ReplicaSet. Asserting readyReplicas == spec.replicas (rather than "every visible
    pod is healthy") is what actually catches a rejected auth-proxy container.
    """
    deployment = k8s_apps_v1_client.read_namespaced_deployment(GRAFANA_DEPLOYMENT_NAME, NAMESPACE)
    desired = deployment.spec.replicas
    ready = deployment.status.ready_replicas or 0
    assert ready == desired, (
        f"{GRAFANA_DEPLOYMENT_NAME} has {ready}/{desired} ready replicas. Check for "
        "FailedCreate events on its ReplicaSet -- a pod rejected by Pod Security "
        "Admission never becomes a Pod object, so it shows up as missing, not unhealthy."
    )


def test_grafana_has_auth_proxy_container(k8s_apps_v1_client):
    """Confirms global.authSidecar.enabled actually wired the auth-proxy container into the pod spec."""
    deployment = k8s_apps_v1_client.read_namespaced_deployment(GRAFANA_DEPLOYMENT_NAME, NAMESPACE)
    container_names = [c.name for c in deployment.spec.template.spec.containers]
    assert "auth-proxy" in container_names, f"Expected an auth-proxy container, got: {container_names}"


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
def _admin_token(_houston_api_module):
    """
    Bootstraps the cluster's one-and-only admin user. createUser's unauthenticated
    signup only ever succeeds once per cluster -- shared by every fixture in this
    module that needs to create a deployment, so it doesn't try to bootstrap a second
    admin and get rejected with "Public sign ups are disabled".
    """
    return create_user(_houston_api_module, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def deployment(_admin_token, _houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """
    Creates a real Airflow Deployment (dagDeployment.type: dag_deploy, so dag-server
    -- and its own auth-sidecar consumer -- gets created too) under this scenario's
    PSS-Restricted + authSidecar overlays, and waits for it to reach full readiness.
    """
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
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"])
    return {"token": token, "id": created["id"], "release_name": created["releaseName"]}


@pytest.mark.flaky(reruns=5, reruns_delay=5, only_rerun=[JWKS_COLD_START_ERROR])
def test_deployment_reaches_ready(deployment):
    """
    The deployment fixture already waits for readiness under PSS-Restricted -- this
    test asserts that contract explicitly. This is the "airflow pods ran into errors"
    gap: PINF-1033-class regressions in houston-api's or airflow-chart's own
    authSidecar injection show up here as pods that never reach ready, the same way a
    rejected container shows up as missing rather than unhealthy (see
    test_grafana_deployment_reaches_ready above).
    """
    assert deployment["release_name"]


def _pod_component(pod, release_name: str) -> str:
    """A stable identity for a pod: its `component` label, or -- for pods some chart versions leave
    unlabeled (e.g. git-sync-relay) -- the pod name with the release prefix and the
    Deployment/StatefulSet hash-or-ordinal suffix stripped (foo-9pkpv/foo-0 -> foo)."""
    label = (pod.metadata.labels or {}).get("component")
    if label:
        return label
    name = pod.metadata.name.removeprefix(f"{release_name}-")
    return re.sub(r"-[a-z0-9]{7,10}-[a-z0-9]{5}$|-[0-9]+$", "", name)


def _auth_proxy_components(core_client, release_name: str) -> set[str]:
    """The set of component identities for every pod in the release carrying an auth-proxy container."""
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    return {_pod_component(pod, release_name) for pod in pods if any(c.name == "auth-proxy" for c in pod.spec.containers)}


def _assert_auth_proxy_components(core_client, release_name: str, expected: set[str]) -> None:
    """Assert the EXACT set of auth-proxy-bearing pods equals `expected`, with a diff on mismatch."""
    actual = _auth_proxy_components(core_client, release_name)
    assert actual == expected, (
        f"Set of pods carrying an auth-proxy container changed for release {release_name!r} -- "
        "re-confirm authSidecar wiring, then update the expected set only if the change is intended.\n"
        f"  expected:             {sorted(expected)}\n"
        f"  actual:               {sorted(actual)}\n"
        f"  unexpectedly present: {sorted(actual - expected)}\n"
        f"  unexpectedly missing: {sorted(expected - actual)}"
    )


def test_deployment_has_auth_proxy_containers(deployment, _k8s_core_v1_client_module):
    """
    Confirms authSidecar reached the Airflow-Deployment-namespace tier in the dag_deploy stage
    (the houston-injected web component plus dag-server's independently-injected copy), not just
    the platform namespace test_grafana_has_auth_proxy_container already covers.

    Asserts the EXACT set of auth-proxy-bearing pods, not "at least one": the PINF-1033-class
    regression this scenario exists for was a consumer silently losing its sidecar, which an
    at-least-one check passes right through.
    """
    _assert_auth_proxy_components(_k8s_core_v1_client_module, deployment["release_name"], AUTH_PROXY_COMPONENTS_DAG_DEPLOY)


@pytest.fixture(scope="module")
def git_sync_deployment(deployment, _houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """
    Switches the SAME deployment from dagDeployment.type: dag_deploy to git_sync (via
    upsertDeployment on deployment["id"]), rather than creating a second, independent
    Airflow Deployment -- see module docstring for why. Exercises git-sync-relay, the
    third and last authSidecar consumer, previously undocumented as a gap rather than
    fixed. A real, reachable repo is required, not just a syntactically-valid URL:
    git-sync-relay's git-daemon container's readiness/liveness/startup probes all check
    for a file a real clone creates (`.git/git-daemon-export-ok`), so an unreachable URL
    would hang the same way an earlier version of this scenario's own readiness wait
    once did (see wait_for_release_ready). astronomer/apc-test-dags-public is a small,
    public, Astronomer-owned fixture repo made for exactly this -- authType HTTPS_NONE,
    no credentials needed, and it's reachable from any CI runner the same way CI already
    reaches GitHub for its own checkout.

    Snapshots the release's workload generations before the switch and passes them to
    wait_for_release_ready: the switch is an update Commander applies asynchronously, so
    without the baseline the wait returns immediately against the still-ready dag_deploy
    workloads -- which is why this fixture previously "passed" while the deployment was still
    running dag_deploy (dag-downloader sidecars) and the git-sync-relay pod the tests below
    assert against had not been created yet.
    """
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
    return {"token": token, "id": created["id"], "release_name": created["releaseName"]}


@pytest.mark.flaky(reruns=5, reruns_delay=5, only_rerun=[JWKS_COLD_START_ERROR])
def test_git_sync_deployment_reaches_ready(git_sync_deployment):
    """
    Readiness here depends on git-sync-relay's git-daemon container actually cloning
    apc-test-dags-public successfully (its probes check for a post-clone marker file),
    so this also incidentally proves the repo choice is reachable from CI, not just
    that PSS-Restricted admits the pod.
    """
    assert git_sync_deployment["release_name"]


def test_git_sync_deployment_has_auth_proxy_container(git_sync_deployment, _k8s_core_v1_client_module):
    """
    Confirms authSidecar reached git-sync-relay -- the third, chart-injected consumer, which this
    scenario only genuinely exercises now that wait_for_release_ready waits for the
    dag_deploy->git_sync switch to reconcile (before, it returned early and this asserted against the
    stale dag_deploy pods, so dag-server's sidecar stood in for the relay's and the check passed
    without a relay ever existing).

    Asserts the EXACT set now expected in the git_sync stage (web component + git-sync-relay, no
    dag-server) -- so the relay losing its sidecar shows up as unexpectedly missing, and a
    dag-server left behind by an incomplete transition shows up as unexpectedly present.
    """
    _assert_auth_proxy_components(_k8s_core_v1_client_module, git_sync_deployment["release_name"], AUTH_PROXY_COMPONENTS_GIT_SYNC)


def test_no_psa_rejection_events(git_sync_deployment, _k8s_core_v1_client_module):
    """
    None of the readiness/container-presence checks above would catch a PSA rejection on
    a one-shot Job or Helm hook (e.g. createUserJob, migrateDatabaseJob) -- those aren't
    Deployments/StatefulSets, so wait_for_release_ready never looks at them, and a
    rejected Job's pod is never created at all rather than showing up unhealthy. Depends
    on git_sync_deployment (the last fixture in this module) so it runs after everything
    this scenario's full lifecycle -- platform install, dag_deploy, and the switch to
    git_sync -- could have created.
    """
    rejections = find_psa_rejection_events(_k8s_core_v1_client_module)
    assert not rejections, "Pod Security Admission rejected at least one object:\n" + "\n".join(rejections)
