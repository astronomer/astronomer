import pytest
import testinfra

# Run with:
#   pytest -k "valid_for and (cp or dp) and not cpdp"
#   pytest -k "valid_for and cpdp"


@pytest.mark.valid_for("cpdp")
@pytest.mark.valid_for("cp", "dp")
def test_nginx(kubernetes_client, current_cluster):
    """
    Test case for nginx that works on both cpdp and cp/dp configurations.
    """
    namespace = "kube-system"  # Replace with your namespace if needed

    # Find the nginx pod by label selector
    pod_name = get_pod_by_label_selector(kubernetes_client, "component=kube-apiserver", namespace)
    assert pod_name, f"No pod with the label 'component=kube-apiserver' found in {current_cluster} cluster."

    # Use testinfra to run commands on the nginx pod
    host = testinfra.get_host(f"kubectl://{pod_name}?container=nginx&namespace={namespace}")
    assert host.check_output("kube-apiserver --help").startswith("The Kubernetes API server validates and configures data")


def get_pod_by_label_selector(core_v1_client, label_selector, namespace="kube-system"):
    """
    Utility function to get a pod name by label selector.
    """
    pods = core_v1_client.list_namespaced_pod(namespace=namespace, label_selector=label_selector).items
    if not pods:
        return None
    return pods[0].metadata.name
