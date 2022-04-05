#!/usr/bin/env python3

from os import getenv

import testinfra

if not (namespace := getenv("NAMESPACE")):
    print("NAMESPACE env var is not present, using 'astronomer' namespace")
    namespace = "astronomer"

if not (release_name := getenv("RELEASE_NAME")):
    print(
        "RELEASE_NAME env var is not present, assuming 'astronomer' is the release name"
    )
    release_name = "astronomer"


def test_non_root(request, kube_client):
    """This is the host fixture for testinfra. To read more, please see
    the testinfra documentation:
    https://testinfra.readthedocs.io/en/latest/examples.html#test-docker-images
    """

    pods = get_pods(kube_client)
    for pod in pods:
        pod_client = testinfra.get_host(
            f"kubectl://{pod}?container=nginx&namespace={namespace}"
        )

        user = pod_client.check_output("whoami")
        assert user != "root"


def get_pods(kube_client, namespace=namespace) -> str:
    """Return the name of a pod found by label selector."""
    pods = kube_client.list_namespaced_pod(namespace).items
    assert len(pods) > 0, "Expected to find at least one pod"
    return pods
