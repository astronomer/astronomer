from os import getenv

from kubernetes import client, config

from tests.utils.k8s import KUBECONFIG_DATA


def test_commander_grpc_ingress_load_balance_annotation():
    """Assert the commander GRPC ingress has the least_conn load-balance annotation applied to the live resource."""
    release_name = getenv("RELEASE_NAME", "astronomer")
    config.load_kube_config(config_file=KUBECONFIG_DATA)
    networking_client = client.NetworkingV1Api()
    ingress = networking_client.read_namespaced_ingress(
        name=f"{release_name}-commander-api-ingress",
        namespace="astronomer",
    )
    annotations = ingress.metadata.annotations
    assert annotations.get("nginx.ingress.kubernetes.io/load-balance") == "least_conn", (
        f"Expected least_conn load balancing on commander GRPC ingress, got: {annotations}"
    )
