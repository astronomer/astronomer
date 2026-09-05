"""Shared assertion for the readonly-root-*-to-* scenarios.

Each of those scenarios creates an Airflow Deployment with one DagDeploymentType, disables
Houston's default readOnlyRootFilesystem for the cluster it's on via updateCluster's
deploymentsConfigOverride (NOT a platform helm upgrade -- see upsert_deployment's and
update_cluster's docstrings in tests/utils/houston_graphql.py for why a helm upgrade alone never
reaches an already-registered cluster's deployments), forces the deployment to re-render, then
switches it to a different DagDeploymentType via upsertDeployment -- the four scenarios differ
only in which DagDeploymentType they start and end on. This is the one assertion all four make in
common: after the transition, no container on the deployment's pods still enforces
readOnlyRootFilesystem.
"""

from kubernetes import client

# A small, public, no-auth fixture repo (astronomer-owned), used by every scenario/test in this
# repo that needs a real git_sync deployment -- see deployment-lifecycle and auth-sidecar.
GIT_SYNC_REPOSITORY_URL = "https://github.com/astronomer/apc-test-dags-public"

# CeleryExecutor's own supporting infrastructure, not Airflow components -- these scenarios are
# scoped to Airflow components specifically, so pods matching one of these substrings are skipped
# entirely rather than asserted against. houston-api hardcodes readOnlyRootFilesystem=true for
# all three unconditionally regardless of deployments.securityContext.container
# (componentsWithSecurityContextOnly in src/lib/deployments/config/index.js never reads the
# override for them), so asserting against them would just be a permanent, known failure that
# tells us nothing about the Airflow-component behavior this scenario actually tests.
_NON_AIRFLOW_COMPONENT_POD_NAME_SUBSTRINGS = ("-redis-", "-statsd-", "-pgbouncer-")


def find_readonly_root_containers(core_client, release_name: str) -> list[str]:
    """Return "pod/container" for every Airflow-component container (including init containers)
    in the release whose securityContext still enforces readOnlyRootFilesystem. Skips pods
    matching _NON_AIRFLOW_COMPONENT_POD_NAME_SUBSTRINGS -- see its comment for why -- and pods
    already marked for deletion (see below).

    Checks the container's own securityContext only -- unlike runAsUser/runAsNonRoot,
    readOnlyRootFilesystem has no pod-level fallback to inherit from (there is no
    pod.spec.security_context.read_only_root_filesystem in the Kubernetes API), so a container
    with no securityContext at all cannot be enforcing it and is correctly not an offender here.

    Skips any pod with metadata.deletion_timestamp set. Confirmed empirically (2026-09-05 CI):
    wait_for_release_ready correctly waits for a Deployment's status fields (updated_replicas ==
    ready_replicas == replicas == spec_replicas) to settle on the new rollout, but a pod
    Kubernetes has already decided to terminate keeps reporting phase=Running/ready=True for the
    rest of its terminationGracePeriodSeconds -- it isn't removed from the API the instant the
    new replica becomes ready, only once its grace period elapses. list_pod_for_all_namespaces()
    can still return that old, on-its-way-out pod in this window even though the Deployment
    itself has genuinely finished rolling out, which is exactly how a stale (pre-switch) copy of
    a component showed up as a false failure here -- correctly settled per Kubernetes, but not
    yet actually gone.
    """
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    offenders = []
    for pod in pods:
        if pod.metadata.deletion_timestamp is not None:
            continue
        if any(substring in pod.metadata.name for substring in _NON_AIRFLOW_COMPONENT_POD_NAME_SUBSTRINGS):
            continue
        # Job-owned pods (e.g. the cleanup CronJob's own spawned pods) are one-shot/point-in-time
        # snapshots wait_for_release_ready never tracks (it only watches Deployments/
        # StatefulSets), so a pod still sitting here from before this test's own config change can
        # look like a live failure when it's really just stale history. Check the owning
        # CronJob/Job's own template instead -- see _find_readonly_root_cronjob_containers.
        if any(owner.kind == "Job" for owner in pod.metadata.owner_references or []):
            continue
        containers = list(pod.spec.containers) + list(pod.spec.init_containers or [])
        for container in containers:
            sc = container.security_context
            if sc and sc.read_only_root_filesystem:
                offenders.append(f"{pod.metadata.name}/{container.name}")
    offenders.extend(_find_readonly_root_cronjob_containers(core_client, release_name))
    return offenders


def _find_readonly_root_cronjob_containers(core_client, release_name: str) -> list[str]:
    """Check every CronJob's own job template (e.g. the airflow-cleanup-pods CronJob) directly,
    rather than any pod it happens to have spawned. Helm/Commander updates a CronJob's template
    immediately on every re-render, the same as a Deployment's -- but the CronJob only creates a
    NEW pod on its own schedule (every 15 minutes by default here), which is far longer than this
    test takes to run. A spawned pod still around at assertion time can be a genuinely stale
    leftover from before this test's own config change, with no way to tell from the pod alone --
    the template is what's actually current.
    """
    batch_client = client.BatchV1Api(core_client.api_client)
    cronjobs = batch_client.list_cron_job_for_all_namespaces(label_selector=f"release={release_name}").items
    offenders = []
    for cronjob in cronjobs:
        pod_spec = cronjob.spec.job_template.spec.template.spec
        containers = list(pod_spec.containers) + list(pod_spec.init_containers or [])
        for container in containers:
            sc = container.security_context
            if sc and sc.read_only_root_filesystem:
                offenders.append(f"{cronjob.metadata.name} (CronJob template)/{container.name}")
    return offenders


def assert_no_readonly_root_containers(core_client, release_name: str) -> None:
    """Assert find_readonly_root_containers() is empty -- the core check of every
    readonly-root-*-to-* scenario, once run after the platform-wide override has taken effect."""
    offenders = find_readonly_root_containers(core_client, release_name)
    assert not offenders, (
        f"Containers still enforcing readOnlyRootFilesystem for release {release_name!r} after "
        f"disabling it platform-wide: {offenders}"
    )
