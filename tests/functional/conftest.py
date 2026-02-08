import os
from pathlib import Path

import pytest
import testinfra
from kubernetes import client, config

from tests.utils.k8s import get_pod_by_label_selector

DEBUG = os.getenv("DEBUG", "").lower() in ["yes", "true", "1"]

KUBECONFIG_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "kubeconfig"
TEST_SCENARIO = os.getenv("TEST_SCENARIO")


@pytest.fixture(scope="function")
def k8s_core_v1_client() -> client.CoreV1Api:
    """
    Provide a Kubernetes core/v1 client for the resolved target cluster.

    :param request: Pytest request object for accessing test metadata.
    :return: A Kubernetes CoreV1Api client for the target cluster.
    """
    kubeconfig_file = str(KUBECONFIG_DIR / TEST_SCENARIO)
    config.load_kube_config(config_file=kubeconfig_file)
    return client.CoreV1Api()


@pytest.fixture(scope="function")
def k8s_apps_v1_client() -> client.AppsV1Api:
    """
    Provide a Kubernetes apps/v1 client for the resolved target cluster.

    :param request: Pytest request object for accessing test metadata.
    :return: A Kubernetes AppsV1Api client for the target cluster.
    """
    kubeconfig_file = str(KUBECONFIG_DIR / TEST_SCENARIO)
    config.load_kube_config(config_file=kubeconfig_file)
    return client.AppsV1Api()


@pytest.fixture(scope="function")
def cp_nginx(k8s_core_v1_client):
    """Fixture for accessing the cp-nginx pod."""
    kubeconfig_file = str(KUBECONFIG_DIR / TEST_SCENARIO)
    pod = get_pod_by_label_selector("astronomer", "component=cp-ingress-controller", kubeconfig_file)
    yield testinfra.get_host(f"kubectl://{pod}?container=nginx&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def dp_nginx(k8s_core_v1_client):
    """Fixture for accessing the dp-nginx pod."""
    kubeconfig_file = str(KUBECONFIG_DIR / TEST_SCENARIO)
    pod = get_pod_by_label_selector("astronomer", "component=dp-ingress-controller", kubeconfig_file)
    yield testinfra.get_host(f"kubectl://{pod}?container=nginx&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def grafana(k8s_core_v1_client):
    """Fixture for accessing the grafana pod."""

    kubeconfig_file = str(KUBECONFIG_DIR / TEST_SCENARIO)
    pod = get_pod_by_label_selector("astronomer", "component=grafana", kubeconfig_file)
    yield testinfra.get_host(f"kubectl://{pod}?container=grafana&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def houston_api(k8s_core_v1_client):
    """Fixture for accessing the houston-api pod."""
    kubeconfig_file = str(KUBECONFIG_DIR / TEST_SCENARIO)
    pod = get_pod_by_label_selector("astronomer", "component=houston", kubeconfig_file)
    yield testinfra.get_host(f"kubectl://{pod}?container=houston&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def prometheus():
    """Fixture for accessing the prometheus pod."""
    kubeconfig_file = str(KUBECONFIG_DIR / TEST_SCENARIO)
    pod = "astronomer-prometheus-0"
    yield testinfra.get_host(f"kubectl://{pod}?container=prometheus&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def es_master():
    """Fixture for accessing the es-master pod."""
    kubeconfig_file = str(KUBECONFIG_DIR / TEST_SCENARIO)
    pod = "astronomer-elasticsearch-master-0"
    yield testinfra.get_host(f"kubectl://{pod}?container=es-master&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def es_data():
    """Fixture for accessing the es-data pod."""
    kubeconfig_file = str(KUBECONFIG_DIR / TEST_SCENARIO)
    pod = "astronomer-elasticsearch-data-0"
    yield testinfra.get_host(f"kubectl://{pod}?container=es-data&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def all_containers(k8s_core_v1_client) -> list[testinfra.host.Host]:
    kubeconfig_file = str(KUBECONFIG_DIR / TEST_SCENARIO)
    all_pods = k8s_core_v1_client.list_namespaced_pod(namespace="astronomer").items
    results = []
    for pod in all_pods:
        results.extend(
            testinfra.get_host(
                f"kubectl://{pod.metadata.name}?container={container.name}&namespace=astronomer",
                kubeconfig=kubeconfig_file,
            )
            for container in pod.spec.containers
        )
    return results
