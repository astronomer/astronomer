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

configs/pin-git-sync-shared-volume-test-images.yaml pins ap-git-sync-relay's repository (not a
specific tag -- see GIT_SYNC_RELAY_IMAGE_PREFIX below) and this airflow-chart branch's build, so
the fix under test actually runs rather than whatever airflowChartVersion ships as the scenario's
default.

shared_volume mode's PVC requires a ReadWriteMany-capable StorageClass, which this scenario's
single-node kind cluster doesn't have by default (see _create_static_shared_volume_pv below and
configs/git-sync-shared-volume-static-storage.yaml) -- each fixture statically pre-binds a
hostPath PersistentVolume for its own release before the PVC is ever created, standing in for
the real network storage (NFS/EFS/Filestore) a production RWX StorageClass would provide.

Structure mirrors deployment-lifecycle/git-sync-private-ca: module-scoped fixtures, since
creating an Airflow Deployment is the expensive part and every test in this file shares its
deployment(s).

Three things this file does NOT cover (see PINF-1194 / the PR #592 critical-review discussion for
why these need a different kind of test than this framework gives cheaply):
  - The concurrent-sync race between the pre-upgrade hook Job and an already-running relay
    Deployment's own poll/webhook cycle -- timing-dependent, not something this fixture's
    upsert-then-wait shape can reliably force to interleave.
  - repoShareMode=shared_volume against a private-CA git host (the PINF-1190 private-CA wiring
    fix) -- git-sync-private-ca already covers private-CA trust for git_daemon mode; a
    shared_volume + private-CA combination would need its own Forgejo-backed fixture, not
    attempted here to keep this scenario scoped to the shared_volume-specific fixes.
  - The SSH and HTTPS+PAT credential-helper wiring -- the actual PINF-1190 reason the init Job
    reuses the ap-git-sync-relay image instead of upstream git-sync. Both deployments here use
    HTTPS_NONE against a public repo, so the credential helper itself is render-tested
    (airflow-chart's own chart tests) but never exercised live by this scenario.
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

# Repository only, not a specific tag -- the tag gets bumped continuously for CVE fixes,
# independently of this scenario, and no other scenario test asserts on an exact image tag.
GIT_SYNC_RELAY_IMAGE_PREFIX = "quay.io/astronomer/ap-git-sync-relay:"

# Known JWKS cold-start race (see git-sync-private-ca's own use of this) -- houston's JWKS cache
# can be cold for the very first token validation after a fresh install, independent of anything
# under test here.
JWKS_COLD_START_ERROR = "13 INTERNAL: failed to validate token"

# Must match configs/git-sync-shared-volume-static-storage.yaml's storageClassName. Deliberately
# not a real StorageClass object -- see _create_static_shared_volume_pv below.
STATIC_STORAGE_CLASS_NAME = "git-sync-shared-volume-test-static"


def _kubectl(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["kubectl", f"--kubeconfig={KUBECONFIG_UNIFIED}", *args], text=True, capture_output=True, input=input_text
    )
    if result.returncode != 0:
        raise AssertionError(f"kubectl {' '.join(args)} failed (exit {result.returncode}):\n{result.stdout}{result.stderr}")
    return result


def _fix_static_shared_volume_pv_hostpath_permissions(release_name: str) -> None:
    """chmod the hostPath directory backing this release's static PV so git-sync-relay's
    non-root init container can actually write into it.

    `gitSyncRelay.securityContext` runs the init hook Job's container as `runAsUser: 50000`
    with a pod-level `fsGroup: 65533` meant to grant it write access. But Kubernetes does not
    apply `fsGroup`-based ownership fixups to `hostPath` volumes -- a deliberate, long-standing
    limitation (unlike most real network/CSI-backed RWX volumes, where fsGroup does apply). The
    directory kubelet creates via the PV's `DirectoryOrCreate` stays root:root 0755, so uid 50000
    can't write into it: `git-sync-once` fails immediately with a permission error (surfaced only
    as a bare `exit_code: 1`, `reason: Error`, no message -- confirmed by reading the raw
    CircleCI build log for build 302666, since this sandbox has no CircleCI API/browser access to
    fetch it directly). Same failure class as PINF-156's real NFS/Filestore case (see the
    "owned subdirectory" design discussion in pinf-1115-notes.md), except here it's an artifact
    of this test's hostPath stand-in rather than a real product bug -- a genuine RWX export
    (NFS/EFS/Filestore) doesn't enforce per-UID ownership the way a fresh hostPath dir does.

    Runs a throwaway root-privileged Job that mounts the identical hostPath and chmods it, rather
    than reaching for docker/node-level access from the test process -- portable regardless of
    which container runtime/CI environment actually hosts the node.
    """
    namespace = _deployment_namespace(release_name)
    job_name = f"fix-shared-volume-perms-{release_name}"
    # `transition_deployment`'s namespace already exists by this point (created earlier for its
    # initial plain deployment); `shared_volume_deployment`'s doesn't yet (Commander hasn't
    # applied anything for it). A leading Namespace doc in the same `apply` is idempotent either
    # way -- unlike `kubectl create namespace`, which would fail outright on the former.
    manifest = f"""
apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
---
apiVersion: batch/v1
kind: Job
metadata:
  name: {job_name}
  namespace: {namespace}
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: chmod
          image: busybox:1.36
          command: ["chmod", "0777", "/mnt/target"]
          securityContext:
            runAsUser: 0
          volumeMounts:
            - name: target
              mountPath: /mnt/target
      volumes:
        - name: target
          hostPath:
            path: /tmp/git-sync-shared-volume-test/{release_name}
            type: DirectoryOrCreate
"""
    _kubectl("apply", "-f", "-", input_text=manifest)
    _kubectl("wait", f"job/{job_name}", "-n", namespace, "--for=condition=complete", "--timeout=60s")


def _create_static_shared_volume_pv(release_name: str) -> None:
    """Pre-bind a hostPath PersistentVolume for this release's git-repo-contents PVC.

    This scenario's kind cluster is single-node with no ReadWriteMany-capable dynamic
    provisioner (its default StorageClass is backed by a local-path-style provisioner that only
    supports ReadWriteOnce/ReadWriteOncePod), and shared_volume mode's PVC hardcodes
    accessModes: [ReadWriteMany] -- a real product requirement (in production, the Airflow
    component pods sharing this volume can land on different nodes), not something to relax for
    this test. So the dynamic-provisioning path can never succeed here, no matter how generous
    the init hook Job's activeDeadlineSeconds is.

    Since every pod in this single-node cluster lands on the same node anyway, a hostPath-backed
    PV serves just as well as real network storage would for proving the fix. This statically
    pre-binds one via claimRef before the PVC exists: static PV/PVC binding only requires
    matching accessModes/capacity/storageClassName (a name that need not correspond to any real
    StorageClass object, see configs/git-sync-shared-volume-static-storage.yaml), so this alone
    gives the PVC somewhere real to bind once the init hook Job creates it.

    Must run after upsert_deployment() returns (so release_name, and therefore the target
    namespace, is known) but before commander's helm install/upgrade for this release actually
    reaches the init hook Job. Commander notices and applies a new/changed deployment
    asynchronously, well after the near-instant kubectl apply below, so there's no real race.
    """
    namespace = _deployment_namespace(release_name)
    _fix_static_shared_volume_pv_hostpath_permissions(release_name)
    manifest = f"""
apiVersion: v1
kind: PersistentVolume
metadata:
  name: git-sync-shared-volume-test-{release_name}
spec:
  accessModes: ["ReadWriteMany"]
  capacity:
    storage: 20Gi
  storageClassName: {STATIC_STORAGE_CLASS_NAME}
  persistentVolumeReclaimPolicy: Retain
  hostPath:
    path: /tmp/git-sync-shared-volume-test/{release_name}
    type: DirectoryOrCreate
  claimRef:
    namespace: {namespace}
    name: git-repo-contents
"""
    _kubectl("apply", "-f", "-", input_text=manifest)


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
    _create_static_shared_volume_pv(created["releaseName"])
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
    _create_static_shared_volume_pv(created["releaseName"])
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


@pytest.mark.flaky(reruns=5, reruns_delay=5, only_rerun=[JWKS_COLD_START_ERROR])
def test_shared_volume_deployment_reaches_ready(shared_volume_deployment):
    """Headline: a fresh-create shared_volume deployment reaches ready, meaning the pre-install
    hook Job populated the PVC successfully before Helm ever applied the Airflow component
    Deployments/StatefulSets that mount it.

    Carries the JWKS-cold-start retry guard: this is the first test to touch the module-scoped
    shared_volume_deployment fixture, and a rerun redoes the fixture's own upsert_deployment
    call too (see git-sync-private-ca's identical use of this)."""
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


def test_shared_volume_init_hook_used_relay_image(shared_volume_deployment, _k8s_batch_v1_client_module):
    """The init hook Job succeeded and used the ap-git-sync-relay image family -- the core
    PINF-1190 change (the hook previously used the upstream git-sync image, which has no
    equivalent of the relay's HTTPS+PAT credential helper). Checks the repository only, not a
    specific tag: the tag gets bumped continuously for CVE fixes independently of this scenario,
    and no other scenario test asserts on an exact image tag."""
    release_name = shared_volume_deployment["release_name"]
    namespace = _deployment_namespace(release_name)
    jobs = _k8s_batch_v1_client_module.list_namespaced_job(namespace, label_selector="component=git-sync-relay").items
    init_jobs = [j for j in jobs if j.metadata.name.endswith("-git-sync-relay-init")]
    assert init_jobs, f"No git-sync-relay-init Job found in {namespace}"
    job = init_jobs[0]
    assert job.status.succeeded == 1, f"init Job did not succeed: status={job.status}"
    image = job.spec.template.spec.containers[0].image
    assert image.startswith(GIT_SYNC_RELAY_IMAGE_PREFIX), (
        f"init Job container image {image!r} is not from {GIT_SYNC_RELAY_IMAGE_PREFIX!r} -- "
        "expected the ap-git-sync-relay image, not upstream git-sync"
    )


@pytest.mark.flaky(reruns=5, reruns_delay=5, only_rerun=[JWKS_COLD_START_ERROR])
def test_pvc_created_on_transition_to_shared_volume(transition_deployment, _k8s_core_v1_client_module):
    """The PVC install-vs-upgrade lifecycle fix: a deployment created plain and then upgraded to
    shared_volume mode gets the git-repo-contents PVC created via the pre-upgrade hook, and it's
    Bound -- before the fix, the PVC's hook was pre-install only and this transition would leave
    the Job with nothing to mount.

    Carries the JWKS-cold-start retry guard: this is the first test to touch the module-scoped
    transition_deployment fixture, and a rerun redoes both of the fixture's own
    upsert_deployment calls too (see git-sync-private-ca's identical use of this)."""
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
