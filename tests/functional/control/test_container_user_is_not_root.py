import pytest
import testinfra

from tests.utils.k8s import get_pod_running_containers
from tests.utils.k8s import kubeconfig_control as kubeconfig

container_ignore_list = [
    "kube-state",
    "houston",
]


def test_container_non_root(control, cluster_name):
    container_list = get_pod_running_containers(kubeconfig=str(kubeconfig), namespace="astronomer")
    for container in container_list.values():
        if container["_name"] in container_ignore_list:
            pytest.skip("Info: Unsupported container: " + container["_name"])

        pod_client = testinfra.get_host(
            f"kubectl://{container['pod_name']}?container={container['_name']}&namespace={container['namespace']}",
            kubeconfig=str(control),
        )

        user_info = pod_client.user()
        assert user_info.name != "root"
        assert user_info.group != "root"
        assert user_info.gid != 0
        assert user_info.uid != 0
