#!/usr/bin/env python3
"""
This file is for system testing the Astronomer Helm chart.

Testinfra is used to create test fixures.

testinfra simplifies and provides syntactic sugar for doing
execs into a running pods.
"""

import json
import os
import pytest
import testinfra
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

def test_prometheus_user(prometheus):
    """ Ensure user is 'nobody'
    """
    user = prometheus.check_output('whoami')
    assert user == "nobody", \
        f"Expected prometheus to be running as 'nobody', not '{user}'"

def test_houston_config(houston_api):
    """ Make assertions about Houston's configuration
    """
    data = houston_api.check_output("echo \"config = require('config'); console.log(JSON.stringify(config))\" | node -")
    houston_config = json.loads(data)
    assert 'url' not in houston_config['nats'].keys(), \
        f"Did not expect to find 'url' configured for 'nats'. Found:\n\n{houston_config['nats']}"
    assert len(houston_config['nats']['servers']), \
        f"Expected to find 'servers' configured for 'nats'. Found:\n\n{houston_config['nats']}"
    for server in houston_config['nats']:
        assert 'localhost' not in server, \
            f"Expected not to find 'localhost' in the 'servers' configuration. Found:\n\n{houston_config['nats']}"


def test_prometheus_targets(prometheus):
    """ Ensure all Prometheus targets are healthy
    """
    data = prometheus.check_output("wget -qO- http://localhost:9090/api/v1/targets")
    targets = json.loads(data)['data']['activeTargets']
    for target in targets:
        assert target['health'] == 'up', \
            'Expected all prometheus targets to be up. ' + \
            'Please check the "targets" view in the Prometheus UI' + \
            f" Target data from the one that is not up:\n\n{target}"

def test_houston_metrics_are_collected(prometheus):
    """ Ensure Houston metrics are collected and prefixed with 'houston_'
    """
    data = prometheus.check_output("wget -qO- http://localhost:9090/api/v1/query?query=houston_up")
    parsed = json.loads(data)
    assert len(parsed['data']['result']) > 0, \
        f"Expected to find a metric houston_up, but we got this response:\n\n{parsed}"

# Create a test fixture for the prometheus pod
@pytest.fixture(scope='session')
def houston_api(request):
    """ This is the host fixture for testinfra. To read more, please see
    the testinfra documentation:
    https://testinfra.readthedocs.io/en/latest/examples.html#test-docker-images
    """
    namespace = os.environ.get('NAMESPACE')
    release_name = os.environ.get('RELEASE_NAME')
    if not namespace:
        print("NAMESPACE env var is not present, using 'default' namespace")
        namespace = 'default'
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
        print("NAMESPACE env var is not present, using 'default' namespace")
        namespace = 'default'
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
