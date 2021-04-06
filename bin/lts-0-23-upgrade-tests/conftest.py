#!/usr/bin/env python3

import pytest
import docker
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


@pytest.fixture(scope="session")
def docker_client(request):
    """This is a text fixture for the docker client,
    should it be needed in a test
    """
    client = docker.from_env()
    yield client
    client.close()


@pytest.fixture(scope="session")
def kube_client(request):
    yield create_kube_client()
