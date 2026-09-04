"""Shared assertion for the readonly-root-* scenario(s).

Each creates a real Airflow Deployment, disables Houston's default readOnlyRootFilesystem for
the cluster it's on via updateCluster's deploymentsConfigOverride (NOT a platform helm upgrade
-- see upsert_deployment's and update_cluster's docstrings in tests/utils/houston_graphql.py for
why a helm upgrade alone never reaches an already-registered cluster's deployments), and forces
the deployment to re-render. The one assertion made in common: Airflow's own components
(scheduler/webserver/worker/triggerer and their init containers) no longer enforce
readOnlyRootFilesystem afterward.

Scoped to Airflow components specifically -- the feature under test is disabling
readOnlyRootFilesystem in Airflow Deployments, not in every sidecar/helper Houston or the chart
happens to also run alongside them. Confirmed in houston-api (deployments/config/index.js) that
readOnlyRootFilesystem is unconditionally hardcoded true, never consulting the override at all,
for three categories that are NOT Airflow's own processes:
  - pgbouncer/redis/statsd: CeleryExecutor's own supporting infrastructure
    (componentsWithSecurityContextOnly).
  - the git-sync/git-sync-init sidecars and the dedicated git-sync-relay pod: Astronomer's
    git_sync DAG-delivery mechanism (gitSyncObjects.dags.gitSync.securityContext).
  - the dag-downloader sidecar and the dedicated dag-server pod: Astronomer's dag_deploy
    DAG-delivery mechanism (dagServerSidecarConfig).
Asserting against any of these would just be a permanent, known failure baked into this
houston-api version that says nothing about whether Airflow's own components -- the actual
feature under test -- pick up the change.
"""

# Pods that are entirely non-Airflow infrastructure/helpers -- skipped outright.
_NON_AIRFLOW_POD_NAME_SUBSTRINGS = ("-redis-", "-statsd-", "-pgbouncer-", "-git-sync-relay-", "-dag-server-")

# Sidecar containers Astronomer injects onto otherwise-Airflow pods (e.g. the scheduler pod also
# carries a "git-sync" container) -- skipped by name, without skipping the pod's own Airflow
# container (e.g. "scheduler") alongside them.
_NON_AIRFLOW_CONTAINER_NAMES = ("git-sync", "git-sync-init", "dag-downloader")


def find_readonly_root_containers(core_client, release_name: str) -> list[str]:
    """Return "pod/container" for every Airflow-component container (including init containers)
    in the release whose securityContext still enforces readOnlyRootFilesystem. Skips
    non-Airflow pods/sidecars -- see this module's docstring for why.

    Checks the container's own securityContext only -- unlike runAsUser/runAsNonRoot,
    readOnlyRootFilesystem has no pod-level fallback to inherit from (there is no
    pod.spec.security_context.read_only_root_filesystem in the Kubernetes API), so a container
    with no securityContext at all cannot be enforcing it and is correctly not an offender here.
    """
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    offenders = []
    for pod in pods:
        if any(substring in pod.metadata.name for substring in _NON_AIRFLOW_POD_NAME_SUBSTRINGS):
            continue
        containers = list(pod.spec.containers) + list(pod.spec.init_containers or [])
        for container in containers:
            if container.name in _NON_AIRFLOW_CONTAINER_NAMES:
                continue
            sc = container.security_context
            if sc and sc.read_only_root_filesystem:
                offenders.append(f"{pod.metadata.name}/{container.name}")
    return offenders


def assert_no_readonly_root_containers(core_client, release_name: str) -> None:
    """Assert find_readonly_root_containers() is empty -- the core check of every
    readonly-root-* scenario, once run after the override has taken effect."""
    offenders = find_readonly_root_containers(core_client, release_name)
    assert not offenders, (
        f"Airflow-component containers still enforcing readOnlyRootFilesystem for release "
        f"{release_name!r} after disabling it: {offenders}"
    )
