import os
from pathlib import Path

import pytest
import testinfra
import yaml
from kubernetes import client, config

from tests.utils.k8s import get_pod_by_label_selector

DEBUG = os.getenv("DEBUG", "").lower() in ["yes", "true", "1"]

KUBECONFIG_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "kubeconfig"
FUNCTIONAL_DIR = Path(__file__).parent
TOPOLOGIES = ("unified", "control", "data")


def _topology_for(test_path: Path) -> str:
    """
    Infer install topology from a test's own location, rather than an env var.

    Tests directly under tests/functional/<unified|control|data>/ are self-evidently
    that topology. Tests under the open-ended scenario mechanism,
    tests/functional/scenarios/<name>/, declare their topology in that scenario's own
    test_profile.yaml.
    """
    parts = Path(test_path).relative_to(FUNCTIONAL_DIR).parts
    if parts[0] in TOPOLOGIES:
        return parts[0]
    if parts[0] == "scenarios":
        profile_path = FUNCTIONAL_DIR / "scenarios" / parts[1] / "test_profile.yaml"
        return yaml.safe_load(profile_path.read_text())["topology"]
    raise RuntimeError(
        f"Could not infer topology for test at {test_path} -- expected it under "
        "tests/functional/{unified,control,data}/ or tests/functional/scenarios/<name>/"
    )


@pytest.fixture(scope="function")
def kubeconfig_file(request) -> str:
    """This test's kubeconfig path, inferred from where the test lives (see _topology_for)."""
    return str(KUBECONFIG_DIR / _topology_for(request.node.path))


@pytest.fixture(scope="function")
def k8s_core_v1_client(kubeconfig_file) -> client.CoreV1Api:
    """Provide a Kubernetes core/v1 client for the resolved target cluster."""
    config.load_kube_config(config_file=kubeconfig_file)
    return client.CoreV1Api()


@pytest.fixture(scope="function")
def k8s_apps_v1_client(kubeconfig_file) -> client.AppsV1Api:
    """Provide a Kubernetes apps/v1 client for the resolved target cluster."""
    config.load_kube_config(config_file=kubeconfig_file)
    return client.AppsV1Api()


@pytest.fixture(scope="function")
def cp_nginx(kubeconfig_file, k8s_core_v1_client):
    """Fixture for accessing the cp-nginx pod."""
    pod = get_pod_by_label_selector("astronomer", "component=cp-ingress-controller", kubeconfig_file)
    yield testinfra.get_host(f"kubectl://{pod}?container=nginx&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def dp_nginx(kubeconfig_file, k8s_core_v1_client):
    """Fixture for accessing the dp-nginx pod."""
    pod = get_pod_by_label_selector("astronomer", "component=dp-ingress-controller", kubeconfig_file)
    yield testinfra.get_host(f"kubectl://{pod}?container=nginx&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def grafana(kubeconfig_file, k8s_core_v1_client):
    """Fixture for accessing the grafana pod."""
    pod = get_pod_by_label_selector("astronomer", "component=grafana", kubeconfig_file)
    yield testinfra.get_host(f"kubectl://{pod}?container=grafana&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def houston_api(kubeconfig_file, k8s_core_v1_client):
    """Fixture for accessing the houston-api pod."""
    pod = get_pod_by_label_selector("astronomer", "component=houston", kubeconfig_file)
    yield testinfra.get_host(f"kubectl://{pod}?container=houston&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def prometheus(kubeconfig_file):
    """Fixture for accessing the prometheus pod."""
    pod = "astronomer-prometheus-0"
    yield testinfra.get_host(f"kubectl://{pod}?container=prometheus&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def es_master(kubeconfig_file):
    """Fixture for accessing the es-master pod."""
    pod = "astronomer-elasticsearch-master-0"
    yield testinfra.get_host(f"kubectl://{pod}?container=es-master&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def es_data(kubeconfig_file):
    """Fixture for accessing the es-data pod."""
    pod = "astronomer-elasticsearch-data-0"
    yield testinfra.get_host(f"kubectl://{pod}?container=es-data&namespace=astronomer", kubeconfig=kubeconfig_file)


@pytest.fixture(scope="function")
def all_containers(kubeconfig_file, k8s_core_v1_client) -> list[testinfra.host.Host]:
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
