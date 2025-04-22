import os
import tempfile
import subprocess
import pytest
from kubernetes import client, config


def run_command(command):
    """Run a shell command and capture its output."""
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {command}\n{result.stderr}")
    return result.stdout.strip()


@pytest.fixture(scope="session")
def create_kind_cluster():
    """Fixture to create and destroy a KIND cluster."""

    def _create_cluster(cluster_name):
        kubeconfig_file = tempfile.NamedTemporaryFile(delete=False)
        kubeconfig_file.close()
        try:
            # Create a KIND cluster
            run_command(f"kind create cluster --name {cluster_name} --kubeconfig {kubeconfig_file.name}")
            yield kubeconfig_file.name
        finally:
            # Cleanup the KIND cluster
            run_command(f"kind delete cluster --name {cluster_name}")
            os.unlink(kubeconfig_file.name)

    return _create_cluster


@pytest.fixture(scope="session")
def cp_cluster(create_kind_cluster):
    """Fixture to create and provide the 'cp' KIND cluster."""
    yield from create_kind_cluster("cp")


@pytest.fixture(scope="session")
def dp_cluster(create_kind_cluster):
    """Fixture to create and provide the 'dp' KIND cluster."""
    yield from create_kind_cluster("dp")


@pytest.fixture(scope="session")
def cpdp_cluster(create_kind_cluster):
    """Fixture to create a KIND cluster to hold both the cp and dp roles."""
    yield from create_kind_cluster("cpdp")


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
