"""git-sync-shared-volume (PINF-1115/1190): validates the git-sync repoShareMode=shared_volume
fix end to end. Before this fix, an Airflow component pod could mount the git-repo-contents PVC's
`dags` subPath before git-sync-relay's own Deployment had done its first clone, producing "Stale
file handle" (ESTALE) -- or, on a release that newly enabled shared_volume mode via `helm upgrade`
rather than at initial install, the pre-install-only PVC hook never ran at all and the Job failed
outright. The fix (astronomer/airflow-chart#592) adds a pre-install/pre-upgrade Helm hook Job that
populates the PVC via git-sync-relay's one-shot `git-sync-once` entrypoint (PINF-1188) before any
consumer Deployment mounts it, and (PINF-1190 critical-review round) gates the PVC's own creation
on a `lookup` check so it's also created on a mode-switch upgrade without ever destroying an
existing one.

configs/pin-git-sync-shared-volume-test-images.yaml pins ap-git-sync-relay:0.5.0 and this
airflow-chart branch's build, so the fix under test actually runs rather than whatever
airflowChartVersion/gitSyncRelay tag ships as the scenario's default.

Structure mirrors deployment-lifecycle/git-sync-private-ca: module-scoped fixtures, since
creating an Airflow Deployment is the expensive part and every test in this file shares its
deployment(s).

Two things this file does NOT cover (see PINF-1194 / the PR #592 critical-review discussion for
why these need a different kind of test than this framework gives cheaply):
  - The concurrent-sync race between the pre-upgrade hook Job and an already-running relay
    Deployment's own poll/webhook cycle -- timing-dependent, not something this fixture's
    upsert-then-wait shape can reliably force to interleave.
  - repoShareMode=shared_volume against a private-CA git host (the PINF-1190 private-CA wiring
    fix) -- git-sync-private-ca already covers private-CA trust for git_daemon mode; a
    shared_volume + private-CA combination would need its own Forgejo-backed fixture, not
    attempted here to keep this scenario scoped to the shared_volume-specific fixes.
"""

import subprocess

import pytest

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

# A public, no-auth repo -- same one deployment-lifecycle (TC-CA-05a) uses -- so the relay clones
# with no credentials and this scenario needs no private-CA/PAT fixture of its own.
GIT_SYNC_REPOSITORY_URL = "https://github.com/astronomer/apc-test-dags-public"

ADMIN_EMAIL = "pinf-1115-git-sync-shared-volume@astronomer.io"
ADMIN_PASSWORD = "Astronomer%123"
WORKSPACE_LABEL = "pinf-1115-git-sync-shared-volume"
FRESH_DEPLOYMENT_LABEL = "pinf-1115-shared-volume-fresh"
TRANSITION_DEPLOYMENT_LABEL = "pinf-1115-shared-volume-transition"

EXPECTED_GIT_SYNC_RELAY_TAG = "0.5.0"


def _kubectl(*args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["kubectl", f"--kubeconfig={KUBECONFIG_UNIFIED}", *args], text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"kubectl {' '.join(args)} failed (exit {result.returncode}):\n{result.stdout}{result.stderr}")
    return result


@pytest.fixture(scope="module")
def _k8s_apps_v1_client_module():
    from kubernetes import client, config

    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def _k8s_core_v1_client_module():
    from kubernetes import client, config

    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def _k8s_batch_v1_client_module():
    from kubernetes import client, config

    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.BatchV1Api()


@pytest.fixture(scope="module")
def _houston_api_module():
    import testinfra

    pod = get_pod_by_label_selector("astronomer", "component=houston", KUBECONFIG_UNIFIED)
    return testinfra.get_host(f"kubectl://{pod}?container=houston&namespace=astronomer", kubeconfig=KUBECONFIG_UNIFIED)


@pytest.fixture(scope="module")
def _admin_token(_houston_api_module):
    """The cluster's one-and-only admin (createUser's unauthenticated signup only works once)."""
    return create_user(_houston_api_module, ADMIN_EMAIL, ADMIN_PASSWORD)


def _deployment_namespace(release_name: str) -> str:
    """The Airflow Deployment namespace is astronomer-<release>, not the release name itself."""
    return f"astronomer-{release_name}"


def _scheduler_pod(core_client, release_name: str):
    """The scheduler pod for a release. Filter by pod NAME containing 'scheduler', not a
    `component=scheduler` label -- git-sync-relay pods are already known to carry no
    `component` label at all (see the private-ca scenario's _relay_pod), so the same
    defensive approach is used here rather than assuming Airflow component pods do."""
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    scheduler = [p for p in pods if "scheduler" in p.metadata.name]
    assert scheduler, f"No scheduler pod for release {release_name!r} (pods: {[p.metadata.name for p in pods]})"
    return scheduler[0]


@pytest.fixture(scope="module")
def shared_volume_deployment(_admin_token, _houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """One Airflow Deployment created directly as git_sync + repoShareMode=shared_volume.

    Created fresh (not transitioned into shared_volume) for the headline readiness assertion --
    a fresh create has no prior all-ready state to short-circuit wait_for_release_ready's poll,
    so it genuinely waits for the whole topology (including the pre-install hook Job succeeding)
    to come up. The install-then-upgrade-into-shared_volume transition is exercised separately by
    the transition_deployment fixture below, which is the actual thing under test for the PVC
    install-vs-upgrade lifecycle fix.
    """
    token = _admin_token
    workspace_id = create_workspace(_houston_api_module, token, WORKSPACE_LABEL)
    cluster_id = get_cluster_id(_houston_api_module, token)
    try:
        created = upsert_deployment(
            _houston_api_module,
            token,
            executor="CeleryExecutor",
            label=FRESH_DEPLOYMENT_LABEL,
            workspace_id=workspace_id,
            cluster_id=cluster_id,
            dag_deployment_type="git_sync",
            repository_url=GIT_SYNC_REPOSITORY_URL,
            auth_type="HTTPS_NONE",
            git_sync_repo_share_mode="shared_volume",
        )
    except HoustonError:
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    # Helm blocks applying the release's Deployments/StatefulSets until the pre-install hook Job
    # succeeds, so reaching this point at all already proves the hook Job populated the PVC --
    # if it had failed, the whole helm install would have failed and no workloads would exist to
    # wait for below (unlike git_daemon mode, shared_volume's git-sync container has no
    # clone-gated readiness probe of its own to lean on for this, per PINF-1194).
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"])
    return {"token": token, "id": created["id"], "release_name": created["releaseName"]}


@pytest.fixture(scope="module")
def transition_deployment(_admin_token, _houston_api_module, _k8s_apps_v1_client_module, _k8s_core_v1_client_module):
    """A second, separate Airflow Deployment: created plain (no git-sync), then upgraded to
    git_sync + repoShareMode=shared_volume on the SAME deployment_uuid.

    This is the actual PVC install-vs-upgrade lifecycle fix under test: before the fix, the PVC's
    Helm hook was pre-install only, so a release that enables shared_volume mode via an upgrade
    (rather than at initial install, like shared_volume_deployment above) would never get the PVC
    created and the Job would fail trying to mount it. LocalExecutor (no Celery workers/redis)
    keeps this second deployment's pod count -- and so the scenario node's scheduling headroom --
    small, since it coexists with shared_volume_deployment's CeleryExecutor deployment (see
    PINF-1080 / the reduce-resources overlay).
    """
    token = _admin_token
    workspace_id = create_workspace(_houston_api_module, token, f"{WORKSPACE_LABEL}-transition")
    cluster_id = get_cluster_id(_houston_api_module, token)
    try:
        created = upsert_deployment(
            _houston_api_module,
            token,
            executor="LocalExecutor",
            label=TRANSITION_DEPLOYMENT_LABEL,
            workspace_id=workspace_id,
            cluster_id=cluster_id,
            dag_deployment_type="image",
        )
    except HoustonError:
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    wait_for_release_ready(_k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"])

    # Now the actual transition: switch this existing deployment to git_sync + shared_volume.
    before = snapshot_release_revisions(_k8s_apps_v1_client_module, created["releaseName"])
    try:
        upsert_deployment(
            _houston_api_module,
            token,
            executor="LocalExecutor",
            deployment_uuid=created["id"],
            dag_deployment_type="git_sync",
            repository_url=GIT_SYNC_REPOSITORY_URL,
            auth_type="HTTPS_NONE",
            git_sync_repo_share_mode="shared_volume",
        )
    except HoustonError:
        dump_pod_logs(_k8s_core_v1_client_module, "component=houston")
        dump_pod_logs(_k8s_core_v1_client_module, "component=commander")
        raise
    wait_for_release_ready(
        _k8s_apps_v1_client_module, _k8s_core_v1_client_module, created["releaseName"], previous_revisions=before
    )
    return {"token": token, "id": created["id"], "release_name": created["releaseName"]}


def test_shared_volume_deployment_reaches_ready(shared_volume_deployment):
    """Headline: a fresh-create shared_volume deployment reaches ready, meaning the pre-install
    hook Job populated the PVC successfully before Helm ever applied the Airflow component
    Deployments/StatefulSets that mount it."""
    assert shared_volume_deployment["release_name"]


def test_shared_volume_dags_mount_has_no_stale_handle(shared_volume_deployment, _k8s_core_v1_client_module):
    """Direct proof, not just inferred from readiness: the scheduler pod's dags mount is
    actually readable, not the ESTALE symptom this bug reported (`ls: cannot access 'dags':
    Stale file handle`)."""
    release_name = shared_volume_deployment["release_name"]
    namespace = _deployment_namespace(release_name)
    pod = _scheduler_pod(_k8s_core_v1_client_module, release_name).metadata.name
    result = _kubectl("exec", pod, "-n", namespace, "-c", "scheduler", "--", "ls", "-la", "/usr/local/airflow/dags")
    assert "stale file handle" not in result.stdout.lower(), f"dags mount is stale:\n{result.stdout}"
    assert result.stdout.strip(), "dags mount listing was unexpectedly empty"


def test_shared_volume_init_hook_used_pinned_images(shared_volume_deployment, _k8s_batch_v1_client_module):
    """Sanity check that configs/pin-git-sync-shared-volume-test-images.yaml actually took effect
    -- without this, a wrong path/typo in the overlay would silently fall back to the chart's
    default gitSyncRelay tag and this whole scenario would test the wrong version without any
    other test here noticing."""
    release_name = shared_volume_deployment["release_name"]
    namespace = _deployment_namespace(release_name)
    jobs = _k8s_batch_v1_client_module.list_namespaced_job(namespace, label_selector="component=git-sync-relay").items
    init_jobs = [j for j in jobs if j.metadata.name.endswith("-git-sync-relay-init")]
    assert init_jobs, f"No git-sync-relay-init Job found in {namespace}"
    job = init_jobs[0]
    assert job.status.succeeded == 1, f"init Job did not succeed: status={job.status}"
    image = job.spec.template.spec.containers[0].image
    assert image.endswith(f":{EXPECTED_GIT_SYNC_RELAY_TAG}"), (
        f"init Job container image {image!r} does not match the pinned tag "
        f"{EXPECTED_GIT_SYNC_RELAY_TAG!r} -- configs/pin-git-sync-shared-volume-test-images.yaml "
        "may not have taken effect"
    )


def test_pvc_created_on_transition_to_shared_volume(transition_deployment, _k8s_core_v1_client_module):
    """The PVC install-vs-upgrade lifecycle fix: a deployment created plain and then upgraded to
    shared_volume mode gets the git-repo-contents PVC created via the pre-upgrade hook, and it's
    Bound -- before the fix, the PVC's hook was pre-install only and this transition would leave
    the Job with nothing to mount."""
    release_name = transition_deployment["release_name"]
    namespace = _deployment_namespace(release_name)
    pvc = _k8s_core_v1_client_module.read_namespaced_persistent_volume_claim("git-repo-contents", namespace)
    assert pvc.status.phase == "Bound", f"git-repo-contents PVC is not Bound: {pvc.status.phase}"


def test_transition_deployment_dags_mount_has_no_stale_handle(transition_deployment, _k8s_core_v1_client_module):
    """Same direct proof as the fresh-create case, but for the transitioned deployment -- the
    scheduler pod that existed before the switch must see a working, non-stale dags mount after
    the release reconciles to the new shared_volume topology."""
    release_name = transition_deployment["release_name"]
    namespace = _deployment_namespace(release_name)
    pod = _scheduler_pod(_k8s_core_v1_client_module, release_name).metadata.name
    result = _kubectl("exec", pod, "-n", namespace, "-c", "scheduler", "--", "ls", "-la", "/usr/local/airflow/dags")
    assert "stale file handle" not in result.stdout.lower(), f"dags mount is stale:\n{result.stdout}"
    assert result.stdout.strip(), "dags mount listing was unexpectedly empty"
