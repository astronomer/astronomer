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


def test_deployment_has_auth_proxy_containers(deployment, _k8s_core_v1_client_module):
    """
    Confirms authSidecar actually reached the Airflow-Deployment-namespace tier, not
    just the platform namespace test_grafana_has_auth_proxy_container already covers.
    Checks across every pod in the release rather than one hardcoded pod name, since
    which pod carries houston-api's injected auth-proxy (webserver vs. api-server)
    depends on the Astro Runtime version, and dag-server's copy is a second,
    independently-injected container this scenario now also exercises.
    """
    pods = _k8s_core_v1_client_module.list_pod_for_all_namespaces(label_selector=f"release={deployment['release_name']}").items
    assert pods, f"Expected at least one pod for release {deployment['release_name']!r}"
    containers_by_pod = {pod.metadata.name: [c.name for c in pod.spec.containers] for pod in pods}
    pods_with_auth_proxy = [name for name, containers in containers_by_pod.items() if "auth-proxy" in containers]
    assert pods_with_auth_proxy, f"Expected at least one pod with an auth-proxy container, got: {containers_by_pod}"


def _pss_restricted_offenders(pods) -> dict[str, list[str]]:
    """
    Mirrors tests/chart_tests/test_default_chart.py's test_pss_restricted_security_context,
    but against real live pods rather than rendered templates (PINF-986, Group E). This
    scenario's namespace-level `enforce: restricted` PSA labels already prove
    runAsNonRoot/allowPrivilegeEscalation/seccompProfile/capabilities at admission time --
    a pod violating those is never created at all, so re-asserting them here is largely
    redundant with test_no_psa_rejection_events. The one property PSA does NOT check is
    the actual numeric runAsUser (only the runAsNonRoot boolean), which is exactly the
    PINF-986 gap this covers -- and, unlike the chart-render tests, this exercises the
    auth-proxy container specifically: it's injected server-side by houston-api's
    extraContainers() (webserver/api-server pods) and airflow-chart's auth_sidecar_container_spec
    helper (dag-server, git-sync-relay), so no chart-render test in any repo sees it.
    """
    offenders = {}
    for pod in pods:
        pod_sc = pod.spec.security_context
        pod_seccomp = pod_sc.seccomp_profile.type if pod_sc and pod_sc.seccomp_profile else None
        pod_run_as_user = pod_sc.run_as_user if pod_sc else None
        pod_run_as_non_root = pod_sc.run_as_non_root if pod_sc else None
        containers = list(pod.spec.containers) + list(pod.spec.init_containers or [])
        for container in containers:
            container_id = f"{pod.metadata.name}/{container.name}"
            sc = container.security_context
            if sc is None:
                offenders[container_id] = ["no securityContext set"]
                continue
            problems = []
            if sc.allow_privilege_escalation is not False:
                problems.append(f"allowPrivilegeEscalation={sc.allow_privilege_escalation!r}")
            if not sc.capabilities or "ALL" not in (sc.capabilities.drop or []):
                problems.append(f"capabilities.drop={getattr(sc.capabilities, 'drop', None)!r}")
            # runAsUser/runAsNonRoot are set at either the pod or container level and inherited
            # down -- apc-airflow's own pattern (PINF-986 Group A) sets runAsUser at the pod
            # level only, with containers relying on inheritance rather than repeating it.
            run_as_non_root = sc.run_as_non_root if sc.run_as_non_root is not None else pod_run_as_non_root
            if run_as_non_root is not True:
                problems.append(f"runAsNonRoot={run_as_non_root!r}")
            run_as_user = sc.run_as_user if sc.run_as_user is not None else pod_run_as_user
            if run_as_user in (None, 0):
                problems.append(f"runAsUser={run_as_user!r}")
            container_seccomp = sc.seccomp_profile.type if sc.seccomp_profile else None
            if "RuntimeDefault" not in (pod_seccomp, container_seccomp):
                problems.append(f"seccompProfile={container_seccomp!r} (pod-level: {pod_seccomp!r})")
            if problems:
                offenders[container_id] = problems
    return offenders


def test_deployment_pods_have_pss_restricted_security_context(deployment, _k8s_core_v1_client_module):
    """Live-pod counterpart to test_deployment_reaches_ready -- see _pss_restricted_offenders."""
    pods = _k8s_core_v1_client_module.list_pod_for_all_namespaces(label_selector=f"release={deployment['release_name']}").items
    assert pods, f"Expected at least one pod for release {deployment['release_name']!r}"
    offenders = _pss_restricted_offenders(pods)
    assert not offenders, "Containers without a full PSS-Restricted securityContext (container: problems):\n" + "\n".join(
        f"  {key}: {value}" for key, value in sorted(offenders.items())
    )


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
    """
    token = deployment["token"]
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
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"])
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
    Confirms authSidecar reached git-sync-relay's pod specifically -- the one
    implementation test_deployment_has_auth_proxy_containers above doesn't cover, since
    this same deployment had no git-sync-relay pod at all before the type switch
    (dag-server is a separate, independently-gated consumer).
    """
    pods = _k8s_core_v1_client_module.list_pod_for_all_namespaces(
        label_selector=f"release={git_sync_deployment['release_name']}"
    ).items
    assert pods, f"Expected at least one pod for release {git_sync_deployment['release_name']!r}"
    containers_by_pod = {pod.metadata.name: [c.name for c in pod.spec.containers] for pod in pods}
    pods_with_auth_proxy = [name for name, containers in containers_by_pod.items() if "auth-proxy" in containers]
    assert pods_with_auth_proxy, f"Expected at least one pod with an auth-proxy container, got: {containers_by_pod}"


def test_git_sync_deployment_pods_have_pss_restricted_security_context(git_sync_deployment, _k8s_core_v1_client_module):
    """Live-pod counterpart to test_git_sync_deployment_reaches_ready -- see _pss_restricted_offenders.
    Covers git-sync-relay's containers (git-daemon, auth-proxy) specifically, the one
    implementation test_deployment_pods_have_pss_restricted_security_context above doesn't reach."""
    pods = _k8s_core_v1_client_module.list_pod_for_all_namespaces(
        label_selector=f"release={git_sync_deployment['release_name']}"
    ).items
    assert pods, f"Expected at least one pod for release {git_sync_deployment['release_name']!r}"
    offenders = _pss_restricted_offenders(pods)
    assert not offenders, "Containers without a full PSS-Restricted securityContext (container: problems):\n" + "\n".join(
        f"  {key}: {value}" for key, value in sorted(offenders.items())
    )


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
