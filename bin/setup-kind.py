#!/usr/bin/env python3
"""Setup KIND cluster and install Astronomer software for testing."""

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import yaml
from certs import (
    astronomer_private_ca_cert_file,
    astronomer_tls_cert_file,
    astronomer_tls_key_file,
)
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

PREREQUISITES = """You MUST set your environment variable TEST_SCENARIO to one of the following values:
- unified: Install with the unified application mode.
- data: Install the with the dataplane application mode.
- control: Install with the controlplane application mode.
"""

GIT_ROOT_DIR = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)
HELPER_BIN_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "bin"
KIND_EXE = str(HELPER_BIN_DIR / "kind")
KUBECTL_EXE = str(HELPER_BIN_DIR / "kubectl")
CHART_METADATA = yaml.safe_load((Path(GIT_ROOT_DIR) / "metadata.yaml").read_text())
KUBECTL_VERSION = CHART_METADATA["test_k8s_versions"][-2]

if (TEST_SCENARIO := os.getenv("TEST_SCENARIO", "")) not in ["unified", "data", "control"]:
    print("ERROR: TEST_SCENARIO environment variable is not set!", file=sys.stderr)
    print(PREREQUISITES, file=sys.stderr)
    raise SystemExit(1)
KUBECONFIG_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "kubeconfig"
KUBECONFIG_DIR.mkdir(parents=True, exist_ok=True)
KUBECONFIG_FILE = str(KUBECONFIG_DIR / TEST_SCENARIO)
DEBUG = os.getenv("DEBUG", "").lower() in ["yes", "true", "1"]


def run_command(command: str | list) -> str:
    """
    Run a shell command and capture its output.

    Args:
        command: The shell command to execute.

    Returns:
        The standard output from the command.

    Raises:
        RuntimeError: If the command fails.
    """
    if isinstance(command, list):
        command = shlex.join(str(x) for x in command)
    else:
        command = str(command)
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {command}\n{result.stderr}")
    return result.stdout.strip()


def kind_load_docker_images(cluster: str) -> None:
    """
    Load any available docker images into a KIND cluster.

    For any images found in CircleCI config that are also found in the local Docker cache,
    load images into the KIND cluster instead of downloading them from the Docker registry.
    This is useful for local development and testing.

    Args:
        cluster: Name of the KIND cluster to load images into.
    """
    circleci_config = yaml.safe_load((GIT_ROOT_DIR / ".circleci" / "config.yml").read_text())
    image_list = circleci_config["workflows"]["scan-docker-images"]["jobs"][0]["trivy-scan-docker"]["matrix"]["parameters"][
        "docker_image"
    ]

    image_allow_list = {
        "unified": [
            "ap-alertmanager",
            "ap-astro-ui",
            "ap-commander",
            "ap-curator",
            "ap-db-bootstrapper",
            "ap-default-backend",
            "ap-houston-api",
            "ap-init",
            "ap-nats-exporter",
            "ap-nats-server",
            "ap-nats-streaming",
            "ap-nginx",
            "ap-nginx-es",
            "ap-postgres-exporter",
            "ap-postgresql",
            "ap-registry",
        ],
        "control": [
            "ap-alertmanager",
            "ap-astro-ui",
            "ap-curator",
            "ap-db-bootstrapper",
            "ap-default-backend",
            "ap-elasticsearch-exporter",
            "ap-elasticsearch",
            "ap-houston-api",
            "ap-nats-exporter",
            "ap-nginx-es",
            "ap-nginx",
            "ap-postgres-exporter",
            "ap-postgresql",
            "ap-prometheus",
        ],
        "data": [
            "ap-commander",
            "ap-fluentd",
            "ap-init",
            "ap-nats-server",
            "ap-nats-streaming",
            "ap-prometheus",
            "ap-registry",
        ],
    }

    cmd = ["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}"]
    print(f"Listing local Docker images with command: {shlex.join(cmd)}")
    local_docker_images = run_command(cmd).splitlines()

    images_to_load = [
        local_image
        for allow_entry in image_allow_list.get(cluster, [])
        for local_image in local_docker_images
        if allow_entry in local_image and local_image in image_list
    ]

    if not images_to_load:
        print(f"No images found to load for cluster '{cluster}'.")
        return

    for image in images_to_load:
        cmd = [f"{KIND_EXE}", "load", "docker-image", "--name", cluster, image]
        print(f"Loading Docker images into KIND cluster with command: {shlex.join(cmd)}")
        try:
            run_command(cmd)
        except RuntimeError as e:
            print(f"Failed to load image '{image}' into KIND cluster '{cluster}': {e}")
            continue


def create_kind_cluster() -> None:
    """
    Create a KIND cluster and return its kubeconfig file path.

    Raises:
        RuntimeError: If the cluster creation fails.
    """
    Path(KUBECONFIG_FILE).unlink(missing_ok=True)

    try:
        create_cluster_cmd = [
            f"{KIND_EXE}",
            "create",
            "cluster",
            f"--name={TEST_SCENARIO}",
            f"--kubeconfig={KUBECONFIG_FILE}",
            f"--config={GIT_ROOT_DIR}/tests/kind/calico-config.yaml",
            f"--image=kindest/node:v{KUBECTL_VERSION}",
        ]
        print(f"Creating KIND cluster with command: {shlex.join(create_cluster_cmd)}")
        try:
            run_command(create_cluster_cmd)
        except RuntimeError as e:
            if "already exist for a cluster" in str(e):
                print(f"ABORT: Cluster '{TEST_SCENARIO}' already exists.", file=sys.stderr)
            else:
                raise RuntimeError(f"Failed to create KIND cluster: {e}") from e

        # Apply calico configuration
        configure_calico_command = [
            KUBECTL_EXE,
            f"--kubeconfig={KUBECONFIG_FILE}",
            "--namespace=kube-system",
            "apply",
            f"--filename={GIT_ROOT_DIR}/tests/kind/calico-crds-v{KUBECTL_VERSION.rpartition('.')[0]}.yaml",
        ]
        print(f"Applying Calico configuration with command: {shlex.join(configure_calico_command)}")
        run_command(configure_calico_command)

        # Configure Calico to ignore loose reverse path filtering
        ignore_lrpf_command = [
            KUBECTL_EXE,
            f"--kubeconfig={KUBECONFIG_FILE}",
            "--namespace=kube-system",
            "set",
            "env",
            "daemonset/calico-node",
            "FELIX_IGNORELOOSERPF=true",
        ]
        print(f"Configuring Calico with command: {shlex.join(ignore_lrpf_command)}")
        run_command(ignore_lrpf_command)

        # Wait until all pods are ready
        print("Waiting for all pods to become ready...")
        wait_for_pods_ready()

    except Exception:
        # Cleanup if cluster creation fails
        delete_cluster_cmd = [f"{KIND_EXE}", "delete", "cluster", f"--name={TEST_SCENARIO}"]
        print(f"Cleaning up after failed cluster creation with command: {shlex.join(delete_cluster_cmd)}")
        run_command(delete_cluster_cmd)
        Path(KUBECONFIG_FILE).unlink(missing_ok=True)
        raise


def create_namespace(namespace: str = "astronomer") -> None:
    """
    Create the given namespace.

    Args:
        namespace: Name of the namespace to create.

    Raises:
        RuntimeError: If namespace creation fails.
    """
    cmd = [
        KUBECTL_EXE,
        f"--kubeconfig={KUBECONFIG_FILE}",
        "create",
        "namespace",
        namespace,
    ]
    if DEBUG:
        cmd.append("-v=9")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return
    if "AlreadyExists" in result.stderr:
        return
    raise RuntimeError(f"Failed to create namespace {namespace}: {result.stderr}")


def create_astronomer_tls_secret() -> None:
    """
    Create the astronomer-tls secret in the KIND cluster using self-signed certificates.

    Raises:
        RuntimeError: If secret creation fails.
    """

    secret_name = "astronomer-tls"  # noqa: S105
    cmd = [
        KUBECTL_EXE,
        f"--kubeconfig={KUBECONFIG_FILE}",
        "--namespace=astronomer",
        "create",
        "secret",
        "tls",
        secret_name,
        f"--cert={astronomer_tls_cert_file}",
        f"--key={astronomer_tls_key_file}",
    ]
    if DEBUG:
        cmd.append("-v=9")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create secret {secret_name} in namespace astronomer: {result.stderr}")


def setup_common_cluster_configs() -> None:
    """
    Perform steps that are common to all installation scenarios.
    """
    create_namespace()
    create_astronomer_tls_secret()
    create_private_ca_secret()


def create_private_ca_secret() -> None:
    """
    Create the private-ca secret in the KIND cluster using self-signed certificates.

    Raises:
        RuntimeError: If secret creation fails.
    """

    cmd = [
        KUBECTL_EXE,
        f"--kubeconfig={KUBECONFIG_FILE}",
        "--namespace=astronomer",
        "create",
        "secret",
        "generic",
        "private-ca",
        f"--from-file={astronomer_private_ca_cert_file}",
    ]
    if DEBUG:
        cmd.append("-v=9")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create secret private-ca in namespace astronomer: {result.stderr}")


def wait_for_pods_ready(timeout: int = 300) -> None:
    """
    Wait until all pods in the cluster are in the 'Running' state.

    Args:
        timeout: Maximum time (in seconds) to wait for all pods to be ready.

    Raises:
        RuntimeError: If not all pods are ready within the timeout.
    """
    config.load_kube_config(config_file=KUBECONFIG_FILE)
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


def check_kube_system_health(apps_v1: client.AppsV1Api, max_wait_seconds: int = 60) -> tuple[bool, str]:
    """
    Check if all deployments in the kube-system namespace are at desired replica count, retrying up to max_wait_seconds.

    Args:
        apps_v1: Kubernetes AppsV1Api client
        max_wait_seconds: Maximum total time to wait for healthy deployments (default 60 seconds)

    Returns:
        tuple: (is_healthy, message)
    """
    start_time = time.monotonic()
    interval = 2  # seconds between checks

    while True:
        try:
            deployments = apps_v1.list_namespaced_deployment(namespace="kube-system")
            unhealthy_deployments = [
                f"{deployment.metadata.name} (Ready: {deployment.status.ready_replicas or 0}/{deployment.spec.replicas})"
                for deployment in deployments.items
                if deployment.status.ready_replicas != deployment.spec.replicas
            ]
            if not unhealthy_deployments:
                return True, f"All kube-system deployments in {TEST_SCENARIO} cluster are healthy."
            last_error = None
        except Exception as e:  # noqa: BLE001
            last_error = e

        elapsed = time.monotonic() - start_time
        if elapsed >= max_wait_seconds:
            if last_error:
                return False, f"Failed to check deployment health in {TEST_SCENARIO} cluster: {last_error}"
            return False, f"Unhealthy deployments found after {int(elapsed)}s: {', '.join(unhealthy_deployments)}"
        time.sleep(interval)


if __name__ == "__main__":
    create_kind_cluster()
    setup_common_cluster_configs()

    # Load Docker images into the KIND cluster
    kind_load_docker_images(TEST_SCENARIO)

    # Check deployment health
    config.load_kube_config(config_file=KUBECONFIG_FILE)
    apps_v1 = client.AppsV1Api()
    is_healthy, message = check_kube_system_health(apps_v1)
    if not is_healthy:
        print(f"ERROR: {message}", file=sys.stderr)
        raise SystemExit(1)
    else:
        print(message)

    print(f"KIND cluster '{TEST_SCENARIO}' setup completed successfully.")
