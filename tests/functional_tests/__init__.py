from kubernetes import client, config


def get_core_v1_client(in_cluster=False):
    """Return a Core v1 API client.

    If running in a pod, specify in_cluster=True to use k8s service account."""

    if in_cluster:
        print("Using in cluster kubernetes configuration")
        config.load_incluster_config()
    else:
        print("Using kubectl kubernetes configuration")
        config.load_kube_config()

    return client.CoreV1Api()
