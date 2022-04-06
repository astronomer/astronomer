#!/usr/bin/env python3

from os import getenv

import docker
import pytest
import testinfra
from kubernetes import client, config

if not (namespace := getenv("NAMESPACE")):
    print("NAMESPACE env var is not present, using 'astronomer' namespace")
    namespace = "astronomer"

if not (release_name := getenv("RELEASE_NAME")):
    print(
        "RELEASE_NAME env var is not present, assuming 'astronomer' is the release name"
    )
    release_name = "astronomer"


@pytest.fixture(scope="function")
def nginx(request, kube_client):
    """This is the host fixture for testinfra. To read more, please see
    the testinfra documentation:
    https://testinfra.readthedocs.io/en/latest/examples.html#test-docker-images
    """

    pod = get_pod_by_label_selector(kube_client, "component=ingress-controller")
    yield testinfra.get_host(f"kubectl://{pod}?container=nginx&namespace={namespace}")


@pytest.fixture(scope="function")
def houston_api(request, kube_client):
    """This is the host fixture for testinfra. To read more, please see
    the testinfra documentation:
    https://testinfra.readthedocs.io/en/latest/examples.html#test-docker-images
    """

    pod = get_pod_by_label_selector(kube_client, "component=houston")
    yield testinfra.get_host(f"kubectl://{pod}?container=houston&namespace={namespace}")


@pytest.fixture(scope="function")
def prometheus(request):
    """This is the host fixture for testinfra. To read more, please see
    the testinfra documentation:
    https://testinfra.readthedocs.io/en/latest/examples.html#test-docker-images
    """

    pod = f"{release_name}-prometheus-0"
    yield testinfra.get_host(
        f"kubectl://{pod}?container=prometheus&namespace={namespace}"
    )


@pytest.fixture(scope="function")
def es_master(request):
    pod = f"{release_name}-elasticsearch-master-0"
    yield testinfra.get_host(
        f"kubectl://{pod}?container=es-master&namespace={namespace}"
    )


@pytest.fixture(scope="function")
def es_data(request):
    pod = f"{release_name}-elasticsearch-data-0"
    yield testinfra.get_host(f"kubectl://{pod}?container=es-data&namespace={namespace}")


@pytest.fixture(scope="function")
def es_client(request, kube_client):
    pod = get_pod_by_label_selector(kube_client, "component=elasticsearch,role=client")
    yield testinfra.get_host(
        f"kubectl://{pod}?container=es-client&namespace={namespace}"
    )


@pytest.fixture(scope="session")
def docker_client(request):
    """This is a text fixture for the docker client,
    should it be needed in a test
    """
    docker_client = docker.from_env()
    yield docker_client
    docker_client.close()


@pytest.fixture(scope="session")
def kube_client(request, in_cluster=False):
    """
    Return a kubernetes client. By default, use kube-config. If running in a pod, use k8s service account.
    """

    k8s_client = get_kube_client(in_cluster)
    yield k8s_client


def get_kube_client(in_cluster=False):

    if in_cluster:
        print("Using in cluster kubernetes configuration")
        config.load_incluster_config()
    else:
        print("Using kubectl kubernetes configuration")
        config.load_kube_config()

    return client.CoreV1Api()


def get_pod_by_label_selector(kube_client, label_selector, namespace=namespace) -> str:
    """Return the name of a pod found by label selector."""
    pods = kube_client.list_namespaced_pod(
        namespace, label_selector=label_selector
    ).items
    assert (
        len(pods) > 0
    ), f"Expected to find at least one pod with labels '{label_selector}'"
    return pods[0].metadata.name


def get_pod_running_containers(pod_namespace=namespace):
    """Return the containers from pods found."""
    pods = get_kube_client().list_namespaced_pod(pod_namespace).items

    containers = []
    for pod in pods:
        pod_name = pod.metadata.name
        for container_status in pod.status.container_statuses:
            if container_status.ready:
                container = vars(container_status).copy()
                container["namespace"] = namespace
                container["pod_name"] = pod_name

                containers.append(container)

    return containers
