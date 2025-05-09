import os
import tempfile
import subprocess
import pytest
from tests import git_root_dir
from kubernetes import client, config
import time
from kubernetes.client.exceptions import ApiException


def run_command(command):
    """Run a shell command and capture its output."""
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {command}\n{result.stderr}")
    return result.stdout.strip()


def wait_for_pods_ready(kubeconfig_file, timeout=300):
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


def create_kind_cluster(cluster_name):
    """
    Create a KIND cluster and return its kubeconfig file path.

    :param cluster_name: Name of the KIND cluster.
    :return: Full path to the kubeconfig file.
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


def delete_kind_cluster(cluster_name, kubeconfig_file):
    """
    Delete a KIND cluster and clean up its kubeconfig file.

    :param cluster_name: Name of the KIND cluster.
    :param kubeconfig_file: Path to the kubeconfig file.
    """
    try:
        cmd = f"kind delete cluster --name {cluster_name}"
        print(f"Deleting KIND cluster with command: {cmd}")
        run_command(cmd)
    finally:
        os.unlink(kubeconfig_file)


@pytest.fixture(scope="session")
def control(request):
    """Fixture for the 'control' cluster."""
    if request.node.name == "test_control.py":
        kubeconfig_file = create_kind_cluster("control")
        helm_install(kubeconfig=kubeconfig_file)
        yield kubeconfig_file
        delete_kind_cluster("control", kubeconfig_file)


@pytest.fixture(scope="session")
def data(request):
    """Fixture for the 'data' cluster."""
    if request.node.name == "test_data.py":
        kubeconfig_file = create_kind_cluster("data")
        helm_install(kubeconfig=kubeconfig_file)
        yield kubeconfig_file
        delete_kind_cluster("data", kubeconfig_file)


@pytest.fixture(scope="session")
def unified(request):
    """Fixture for the 'unified' cluster."""
    if request.node.name == "test_unified.py":
        kubeconfig_file = create_kind_cluster("unified")
        helm_install(kubeconfig=kubeconfig_file)
        yield kubeconfig_file
        delete_kind_cluster("unified", kubeconfig_file)


def helm_install(kubeconfig, values=f"{git_root_dir}/configs/local-dev.yaml"):
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
def kubernetes_client(request, clusters):
    """
    Provide a Kubernetes client for the resolved target cluster.
    """
    cluster_name = request.param
    kubeconfig_path = clusters[cluster_name]
    config.load_kube_config(config_file=kubeconfig_path)
    return client.CoreV1Api()
