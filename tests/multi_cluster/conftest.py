import os
import tempfile
import subprocess
import pytest


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
