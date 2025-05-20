import os
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path

import pytest
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from tests import git_root_dir
from tests.utils.cert import cert_file, create_certificates, key_file
from tests.utils.install_ci_tools import install_all_tools

kind_file = Path.home() / ".local" / "share" / "astronomer-software" / "bin" / "kind"
helm_file = Path.home() / ".local" / "share" / "astronomer-software" / "bin" / "helm"
kubeconfig_dir = Path.home() / ".local" / "share" / "astronomer-software" / "kubeconfig"


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
    kubeconfig_file = kubeconfig_dir / f"{cluster_name}"
    if not kubeconfig_file.parent.exists():
        kubeconfig_file.parent.mkdir(parents=True, exist_ok=True)
    kubeconfig_file.unlink(missing_ok=True)
    install_all_tools()

    try:
        cmd = f"{kind_file} create cluster --name {cluster_name} --kubeconfig {kubeconfig_file}"
        print(f"Creating KIND cluster with command: {cmd}")
        run_command(cmd)

        # Wait until all pods are ready
        print("Waiting for all pods to become ready...")
        wait_for_pods_ready(str(kubeconfig_file))

        return str(kubeconfig_file)
    except Exception:
        # Cleanup if cluster creation fails
        cmd = f"{kind_file} delete cluster --name {cluster_name}"
        print(f"Cleaning up after failed cluster creation with command: {cmd}")
        run_command(cmd)
        os.unlink(str(kubeconfig_file))
        raise


def delete_kind_cluster(cluster_name: str, kubeconfig_file: str) -> None:
    """
    Delete a KIND cluster and clean up its kubeconfig file.

    :param cluster_name: Name of the KIND cluster to delete.
    :param kubeconfig_file: Path to the kubeconfig file to clean up.
    """
    try:
        cmd = f"{kind_file} delete cluster --name {cluster_name}"
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
    create_namespace(kubeconfig_file)
    create_tls_secret(kubeconfig_file)
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
    create_namespace(kubeconfig_file)
    create_tls_secret(kubeconfig_file)
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
    create_namespace(kubeconfig_file)
    create_tls_secret(kubeconfig_file)
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
        helm_file,
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
    kubeconfig_file = clusters[cluster_name]
    config.load_kube_config(config_file=kubeconfig_file)
    return client.CoreV1Api()


def create_namespace(kubeconfig_file, namespace="astronomer") -> None:
    """Create the given namespace."""
    if not Path(kubeconfig_file).exists():
        raise FileNotFoundError(f"Kubeconfig file not found at {kubeconfig_file}")

    cmd = [
        "kubectl",
        "--kubeconfig",
        str(kubeconfig_file),
        "create",
        "namespace",
        namespace,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return
    if "AlreadyExists" in result.stderr:
        return
    raise RuntimeError(f"Failed to create namespace {namespace}: {result.stderr}")


def create_tls_secret(kubeconfig_file) -> None:
    """Create a TLS secret in the KIND cluster using self-signed certificates."""
    if not Path(kubeconfig_file).exists():
        raise FileNotFoundError(f"Kubeconfig file not found at {kubeconfig_file}")

    create_certificates()

    secret_name = "astronomer-tls"
    namespace = "astronomer"
    cmd = [
        "kubectl",
        "--kubeconfig",
        str(kubeconfig_file),
        "-n",
        namespace,
        "create",
        "secret",
        "tls",
        secret_name,
        "--cert",
        str(cert_file),
        "--key",
        str(key_file),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create secret {secret_name} in namespace {namespace}: {result.stderr}")
