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

# A small, public, no-auth fixture repo (astronomer-owned), used by every scenario/test in this
# repo that needs a real git_sync deployment -- see deployment-lifecycle and auth-sidecar.
GIT_SYNC_REPOSITORY_URL = "https://github.com/astronomer/apc-test-dags-public"


def find_readonly_root_containers(core_client, release_name: str) -> list[str]:
    """Return "pod/container" for every container (including init containers) in the release
    whose securityContext still enforces readOnlyRootFilesystem.

    Checks the container's own securityContext only -- unlike runAsUser/runAsNonRoot,
    readOnlyRootFilesystem has no pod-level fallback to inherit from (there is no
    pod.spec.security_context.read_only_root_filesystem in the Kubernetes API), so a container
    with no securityContext at all cannot be enforcing it and is correctly not an offender here.
    """
    pods = core_client.list_pod_for_all_namespaces(label_selector=f"release={release_name}").items
    offenders = []
    for pod in pods:
        containers = list(pod.spec.containers) + list(pod.spec.init_containers or [])
        for container in containers:
            sc = container.security_context
            if sc and sc.read_only_root_filesystem:
                offenders.append(f"{pod.metadata.name}/{container.name}")
    return offenders


def assert_no_readonly_root_containers(core_client, release_name: str) -> None:
    """Assert find_readonly_root_containers() is empty -- the core check of every
    readonly-root-*-to-* scenario, once run after the platform-wide override has taken effect."""
    offenders = find_readonly_root_containers(core_client, release_name)
    assert not offenders, (
        f"Containers still enforcing readOnlyRootFilesystem for release {release_name!r} after "
        f"disabling it platform-wide: {offenders}"
    )
