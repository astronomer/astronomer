#!/usr/bin/env python3

import os
import pytest
import docker
import testinfra
from kubernetes import client, config
from kubernetes import client, config

def create_kube_client(in_cluster=False):
    """
    Load and store authentication and cluster information from kube-config
    file; if running inside a pod, use Kubernetes service account. Use that to
    instantiate Kubernetes client.
    """
    if in_cluster:
        print("Using in cluster kubernetes configuration")
        config.load_incluster_config()
    else:
        print("Using kubectl kubernetes configuration")
        config.load_kube_config()
    return client.CoreV1Api()

@pytest.fixture(scope='session')
def nginx(request):
    """ This is the host fixture for testinfra. To read more, please see
    the testinfra documentation:
    https://testinfra.readthedocs.io/en/latest/examples.html#test-docker-images
    """
    namespace = os.environ.get('NAMESPACE')
    release_name = os.environ.get('RELEASE_NAME')
    if not namespace:
        print("NAMESPACE env var is not present, using 'astronomer' namespace")
        namespace = 'astronomer'
    if not release_name:
        print("RELEASE_NAME env var is not present, assuming 'astronomer' is the release name")
        release_name = 'astronomer'
    kube = create_kube_client()
    pods = kube.list_namespaced_pod(namespace, label_selector="component=ingress-controller")
    pods = pods.items
    assert len(pods) > 0, "Expected to find at least one pod with label 'component: ingress-controller'"
    pod = pods[0]
    yield testinfra.get_host(f'kubectl://{pod.metadata.name}?container=nginx&namespace={namespace}')

@pytest.fixture(scope='session')
def houston_api(request):
    """ This is the host fixture for testinfra. To read more, please see
    the testinfra documentation:
    https://testinfra.readthedocs.io/en/latest/examples.html#test-docker-images
    """
    namespace = os.environ.get('NAMESPACE')
    release_name = os.environ.get('RELEASE_NAME')
    if not namespace:
        print("NAMESPACE env var is not present, using 'astronomer' namespace")
        namespace = 'astronomer'
    if not release_name:
        print("RELEASE_NAME env var is not present, assuming 'astronomer' is the release name")
        release_name = 'astronomer'
    kube = create_kube_client()
    pods = kube.list_namespaced_pod(namespace, label_selector=f"component=houston")
    pods = pods.items
    assert len(pods) > 0, "Expected to find at least one pod with label 'component: houston'"
    pod = pods[0]
    yield testinfra.get_host(f'kubectl://{pod.metadata.name}?container=houston&namespace={namespace}')

# Create a test fixture for the prometheus pod
@pytest.fixture(scope='session')
def prometheus(request):
    """ This is the host fixture for testinfra. To read more, please see
    the testinfra documentation:
    https://testinfra.readthedocs.io/en/latest/examples.html#test-docker-images
    """
    namespace = os.environ.get('NAMESPACE')
    release_name = os.environ.get('RELEASE_NAME')
    if not namespace:
        print("NAMESPACE env var is not present, using 'astronomer' namespace")
        namespace = 'astronomer'
    if not release_name:
        print("RELEASE_NAME env var is not present, assuming 'astronomer' is the release name")
        release_name = 'astronomer'
    pod = f'{release_name}-prometheus-0'
    yield testinfra.get_host(f'kubectl://{pod}?container=prometheus&namespace={namespace}')

@pytest.fixture(scope='session')
def docker_client(request):
    """ This is a text fixture for the docker client,
    should it be needed in a test
    """
    client = docker.from_env()
    yield client
    client.close()

@pytest.fixture(scope='session')
def kube_client(request):
    yield create_kube_client()
