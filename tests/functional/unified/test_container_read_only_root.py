# This does not work as long as we are running `runAsNonRoot: true`, and the default user is not root. If either of those were
# were different we could test this, but with those set as they are, we cannot exec into the pod as root to test the ability of root
# to write to the root volume. This seems fine. We can trust that the kubernetes security context is working as expected, so unit
# tests will have to suffice for testing this functionality test.
#
# import os
# from pathlib import Path

# import pytest
# import testinfra
# from kubernetes import client, config

# # This should contain a list of pod name substrings that have been completed in ticket
# # https://github.com/astronomer/issues/issues/7394
# # This should match tests/chart_tests/test_container_read_only_root.py
# read_only_root_pods = [
#     "commander",
# ]

# KUBECONFIG_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "kubeconfig"
# TEST_SCENARIO = os.getenv("TEST_SCENARIO")


# def get_all_containers() -> list[testinfra.host.Host]:
#     kubeconfig_file = str(KUBECONFIG_DIR / TEST_SCENARIO)
#     config.load_kube_config(config_file=kubeconfig_file)
#     k8s_core_v1_client = client.CoreV1Api()
#     all_pods = k8s_core_v1_client.list_namespaced_pod(namespace="astronomer").items
#     results = []
#     for pod in all_pods:
#         results.extend(
#             testinfra.get_host(
#                 f"kubectl://{pod.metadata.name}?container={container.name}&namespace=astronomer",
#                 kubeconfig=kubeconfig_file,
#             )
#             for container in pod.spec.containers
#         )
#     return results


# class TestAllContainersReadOnlyRoot:
#     all_containers = get_all_containers()
#     all_containers_ids = [
#         str(container).removeprefix("<testinfra.host.Host kubectl://astronomer-").removesuffix(">") for container in all_containers
#     ]

#     @pytest.mark.parametrize("container", all_containers, ids=all_containers_ids)
#     def test_root_volume_is_not_writable(self, container):
#         """
#         Check that the root volume is not writable in all containers.
#         """
#         if not container.exists("test"):
#             # Container probably is not running, but in any case it cannot be tested.
#             return
#         if any(x in str(container) for x in read_only_root_pods):
#             assert container.run("test -w /", timeout=5).rc == 1, f"Root volume is writable in {container}"
#         else:
#             # This assertion ensures that this test is updated whenever we change the readOnlyRootFilesystem property
#             assert container.run("test -w /", timeout=5).rc == 0, (
#                 f"Root volume is not writable in {container}, which is unexpected."
#             )
