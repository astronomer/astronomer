from pathlib import Path

from kubernetes import client, config

astronomer_software_dir = Path.home() / ".local" / "share" / "astronomer-software"
kubeconfig_control = astronomer_software_dir / "kubeconfig" / "control"
kubeconfig_data = astronomer_software_dir / "kubeconfig" / "data"
kubeconfig_unified = astronomer_software_dir / "kubeconfig" / "unified"


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


def get_pod_by_label_selector(label_selector, pod_namespace, kubeconfig) -> str:
    """Return the name of a pod found by label selector."""
    k8s_core_v1_client = get_core_v1_client(kubeconfig=kubeconfig)
    pods = k8s_core_v1_client.list_namespaced_pod(pod_namespace, label_selector=label_selector).items
    assert len(pods) > 0, f"Expected to find at least one pod with labels '{label_selector}'"
    return pods[0].metadata.name
