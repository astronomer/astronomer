from pathlib import Path

from kubernetes import client, config

ASTRONOMER_SOFTWARE_DIR = Path.home() / ".local" / "share" / "astronomer-software"
KUBECONFIG_CONTROL = str(ASTRONOMER_SOFTWARE_DIR / "kubeconfig" / "control")
KUBECONFIG_DATA = str(ASTRONOMER_SOFTWARE_DIR / "kubeconfig" / "data")
KUBECONFIG_UNIFIED = str(ASTRONOMER_SOFTWARE_DIR / "kubeconfig" / "unified")


def get_core_v1_client(in_cluster=False, kubeconfig=None):
    """Return a Core v1 API client.

    If running in a pod, specify in_cluster=True to use k8s service account."""

    if in_cluster:
        print("Using in cluster kubernetes configuration")
        config.load_incluster_config()
    else:
        print("Using kubectl kubernetes configuration")
        config.load_kube_config(config_file=kubeconfig)

    return client.CoreV1Api()


def get_pod_running_containers(namespace, kubeconfig=None):
    """Return the containers from pods found."""
    pods = get_core_v1_client(kubeconfig=kubeconfig).list_namespaced_pod(namespace).items

    containers = {}
    for pod in pods:
        pod_name = pod.metadata.name
        for container_status in pod.status.container_statuses:
            if container_status.ready:
                container = vars(container_status).copy()
                container["pod_name"] = pod_name
                container["namespace"] = namespace

                key = f"{pod_name}_{container_status.name}"
                containers[key] = container

    return containers


def get_pod_by_label_selector(namespace, label_selector, kubeconfig) -> str:
    """Return the name of a pod found by label selector."""
    k8s_core_v1_client = get_core_v1_client(kubeconfig=kubeconfig)
    pods = k8s_core_v1_client.list_namespaced_pod(namespace, label_selector=label_selector).items
    assert len(pods) > 0, f"Expected to find at least one pod with labels '{label_selector}'"
    return pods[0].metadata.name


def find_psa_rejection_events(k8s_core_v1_client) -> list[str]:
    """Return one line per Pod Security Admission rejection found anywhere in the cluster.

    A pod PSA rejects is never created -- it never becomes an unhealthy Pod object, only
    a "FailedCreate" Warning Event on whatever tried to create it (a ReplicaSet for a
    Deployment, or the object itself for a bare Job/Helm hook, which has no intermediate
    controller). Readiness checks that only look at Deployment/StatefulSet
    readyReplicas -- e.g. wait_for_release_ready -- can't see this for anything that
    isn't itself a Deployment or StatefulSet: a one-shot Job (createUserJob,
    migrateDatabaseJob) or a Helm hook could be silently rejected by a PSS-Restricted
    namespace without ever blocking, or even appearing in, a release's own readiness.

    Cluster-wide rather than scoped to specific namespaces: each functional-test scenario
    gets its own dedicated kind cluster for the CircleCI job, so there's no other
    scenario's events to accidentally pick up, and this avoids having to know in advance
    every namespace a scenario touches (including one Commander only creates at runtime).
    """
    events = k8s_core_v1_client.list_event_for_all_namespaces().items
    return [
        f"{event.type} {event.reason}: {event.involved_object.namespace}/{event.involved_object.name}: {event.message}"
        for event in events
        if event.reason == "FailedCreate" and "violates PodSecurity" in (event.message or "")
    ]
