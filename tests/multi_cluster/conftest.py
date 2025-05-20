import os
import subprocess
import tempfile
import time
from collections.abc import Iterable

import pytest
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from tests import git_root_dir


def run_command(command: str) -> str:
    """
    Run a shell command and capture its output.

    :param command: The shell command to execute.
    :return: The standard output from the command.
    :raises RuntimeError: If the command fails.
    """
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {command}\n{result.stderr}")
    return result.stdout.strip()


def wait_for_pods_ready(kubeconfig_file: str, timeout: int = 300) -> None:
    """
    Waits until all pods in the cluster are in the 'Running' state.

    :param kubeconfig_file: Path to the kubeconfig file.
    :param timeout: Maximum time (in seconds) to wait for all pods to be ready.
    :raises RuntimeError: If not all pods are ready within the timeout.
    """
    config.load_kube_config(config_file=kubeconfig_file)
    v1 = client.CoreV1Api()

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            pods = v1.list_pod_for_all_namespaces().items
        except ApiException as e:
            print(f"Error fetching pod information: {e}")
            time.sleep(5)
            continue

        all_ready = True
        for pod in pods:
            for container_status in pod.status.container_statuses or []:
                if not container_status.ready:
                    all_ready = False
                    break
            if not all_ready:
                break

        if all_ready:
            print("All pods are in the 'Running' state.")
            return

        print("Waiting for all pods to reach 'Running' state...")
        time.sleep(5)

    raise RuntimeError("Timed out waiting for all pods to reach 'Running' state.")


def create_kind_cluster(cluster_name: str) -> str:
    """
    Create a KIND cluster and return its kubeconfig file path.

    :param cluster_name: Name of the KIND cluster to create.
    :return: Full path to the kubeconfig file.
    :raises RuntimeError: If the cluster creation fails.
    """
    kubeconfig_file = tempfile.NamedTemporaryFile(delete=False)
    kubeconfig_file.close()

    try:
        cmd = f"kind create cluster --name {cluster_name} --kubeconfig {kubeconfig_file.name}"
        print(f"Creating KIND cluster with command: {cmd}")
        run_command(cmd)

        # Wait until all pods are ready
        print("Waiting for all pods to become ready...")
        wait_for_pods_ready(kubeconfig_file.name)

        return kubeconfig_file.name
    except Exception:
        # Cleanup if cluster creation fails
        cmd = f"kind delete cluster --name {cluster_name}"
        print(f"Cleaning up after failed cluster creation with command: {cmd}")
        run_command(cmd)
        os.unlink(kubeconfig_file.name)
        raise


def delete_kind_cluster(cluster_name: str, kubeconfig_file: str) -> None:
    """
    Delete a KIND cluster and clean up its kubeconfig file.

    :param cluster_name: Name of the KIND cluster to delete.
    :param kubeconfig_file: Path to the kubeconfig file to clean up.
    """
    try:
        cmd = f"kind delete cluster --name {cluster_name}"
        print(f"Deleting KIND cluster with command: {cmd}")
        run_command(cmd)
    finally:
        os.unlink(kubeconfig_file)


@pytest.fixture(scope="session")
def control(request) -> Iterable[str]:
    """
    Fixture for the 'control' cluster.

    :param request: Pytest request object for accessing test metadata.
    :yield: Path to the kubeconfig file for the 'control' cluster.
    """
    kubeconfig_file = create_kind_cluster("control")
    helm_install(kubeconfig=kubeconfig_file)
    yield kubeconfig_file
    delete_kind_cluster("control", kubeconfig_file)


@pytest.fixture(scope="session")
def data(request) -> Iterable[str]:
    """
    Fixture for the 'data' cluster.

    :param request: Pytest request object for accessing test metadata.
    :yield: Path to the kubeconfig file for the 'data' cluster.
    """
    kubeconfig_file = create_kind_cluster("data")
    helm_install(kubeconfig=kubeconfig_file)
    yield kubeconfig_file
    delete_kind_cluster("data", kubeconfig_file)


@pytest.fixture(scope="session")
def unified(request) -> Iterable[str]:
    """
    Fixture for the 'unified' cluster.

    :param request: Pytest request object for accessing test metadata.
    :yield: Path to the kubeconfig file for the 'unified' cluster.
    """
    kubeconfig_file = create_kind_cluster("unified")
    helm_install(kubeconfig=kubeconfig_file)
    yield kubeconfig_file
    delete_kind_cluster("unified", kubeconfig_file)


def helm_install(kubeconfig: str, values: str = f"{git_root_dir}/configs/local-dev.yaml") -> None:
    """
    Install a Helm chart using the provided kubeconfig and values file.

    :param kubeconfig: Path to the kubeconfig file.
    :param values: Path to the Helm values file.
    """
    helm_install_command = [
        "helm",
        "install",
        "astronomer",
        "--create-namespace",
        "--namespace=astronomer",
        str(git_root_dir),
        f"--values={values}",
        f"--kubeconfig={kubeconfig}",
        "--wait",
        "--timeout=5m0s",
    ]

    subprocess.run(
        helm_install_command,
        check=True,
    )


@pytest.fixture(scope="function")
def kubernetes_client(request, clusters) -> client.CoreV1Api:
    """
    Provide a Kubernetes client for the resolved target cluster.

    :param request: Pytest request object for accessing test metadata.
    :param clusters: Dictionary of cluster names and their kubeconfig file paths.
    :return: A Kubernetes CoreV1Api client for the target cluster.
    """
    cluster_name = request.param
    kubeconfig_path = clusters[cluster_name]
    config.load_kube_config(config_file=kubeconfig_path)
    return client.CoreV1Api()
