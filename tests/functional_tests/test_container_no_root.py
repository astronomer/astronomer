#!/usr/bin/env python3

import pytest
import testinfra

from tests.functional_tests.conftest import get_pod_running_containers

container_ignore_list = [
    "kube-state",
    "houston",
    "fluentd",
]

container_list = get_pod_running_containers()


@pytest.mark.parametrize(
    "container",
    container_list.values(),
    ids=container_list.keys(),
)
def test_container_non_root(request, container):
    if container["_name"] in container_ignore_list:
        pytest.skip("Info: Unsupported container: " + container["_name"])

    """This is the host fixture for testinfra. To read more, please see
    the testinfra documentation:
    https://testinfra.readthedocs.io/en/latest/examples.html#test-docker-images
    """

    pod_client = testinfra.get_host(
        f"kubectl://{container['pod_name']}?container={container['_name']}&namespace={container['namespace']}"
    )

    user_info = pod_client.user()
    assert user_info.name != "root"
    assert user_info.group != "root"
    assert user_info.gid != 0
    assert user_info.uid != 0
