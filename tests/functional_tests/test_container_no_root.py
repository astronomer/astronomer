#!/usr/bin/env python3

import pytest
import testinfra

from tests.functional_tests.conftest import get_pod_running_containers

container_ignore_list = ["astronomer-kubed", "kube-state", "houston", "flentd", "metrics-exporter"]


@pytest.mark.parametrize(
    "container",
    get_pod_running_containers().values(),
    ids=get_pod_running_containers().keys(),
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

    user = pod_client.check_output("whoami")
    assert user != "root"
