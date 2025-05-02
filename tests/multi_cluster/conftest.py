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
    Waits until all pods in the cluster are in the `1/1 Running` state.

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
            print("All pods are in the '1/1 Running' state.")
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
        "--timeout=600",
    ]

    subprocess.run(
        helm_install_command,
        check=True,
    )


@pytest.fixture(scope="session")
def cp_cluster():
    """Fixture to create and provide the 'cp' KIND cluster with Helm initialization."""
    cluster_name = "cp"
    kubeconfig_file = create_kind_cluster(cluster_name)

    try:
        helm_install(kubeconfig=kubeconfig_file)
        yield kubeconfig_file
    finally:
        delete_kind_cluster(cluster_name, kubeconfig_file)


@pytest.fixture(scope="session")
def dp_cluster():
    """Fixture to create and provide the 'dp' KIND cluster."""
    cluster_name = "dp"
    kubeconfig_file = create_kind_cluster(cluster_name)

    try:
        helm_install(kubeconfig=kubeconfig_file)
        yield kubeconfig_file
    finally:
        delete_kind_cluster(cluster_name, kubeconfig_file)


@pytest.fixture(scope="session")
def cpdp_cluster():
    """Fixture to create a KIND cluster to hold both the cp and dp roles."""
    cluster_name = "cpdp"
    kubeconfig_file = create_kind_cluster(cluster_name)

    try:
        helm_install(kubeconfig=kubeconfig_file)
        yield kubeconfig_file
    finally:
        delete_kind_cluster(cluster_name, kubeconfig_file)


@pytest.fixture(scope="session")
def clusters(cpdp_cluster, cp_cluster, dp_cluster):
    """
    Provide a dictionary of available clusters.
    """
    return {"cpdp": cpdp_cluster, "cp": cp_cluster, "dp": dp_cluster}


@pytest.fixture(scope="function")
def kubernetes_client(request, clusters):
    """
    Provide a Kubernetes client for the resolved target cluster.
    """
    cluster_name = request.param
    kubeconfig_path = clusters[cluster_name]
    config.load_kube_config(config_file=kubeconfig_path)
    return client.CoreV1Api()


def pytest_generate_tests(metafunc):
    """
    Dynamically parameterize tests based on the 'valid_for' marker.
    """
    # Check if 'kubernetes_client' and 'current_cluster' need to be parameterized
    if "kubernetes_client" in metafunc.fixturenames and "current_cluster" in metafunc.fixturenames:
        # Collect all clusters the test is valid for
        valid_clusters = []
        for marker in metafunc.definition.iter_markers(name="valid_for"):
            valid_clusters.extend(marker.args)

        # Pass the clusters as parameterized arguments to the test
        metafunc.parametrize(
            "kubernetes_client, current_cluster",
            [(cluster, cluster) for cluster in valid_clusters],
            indirect=["kubernetes_client"],
        )
