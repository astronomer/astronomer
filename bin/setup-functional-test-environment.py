#!/usr/bin/env python3
"""
Setup functional test environment for Astronomer software testing.

This script creates KIND clusters and installs Astronomer software for testing.
It supports three deployment scenarios: unified, data, and control plane.
"""

### TODO: move all of these "tests" imports into this script because we cannot import them from the tests module and they are not
###       needed there now that this will be a standalone script.

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path, PosixPath
from typing import Literal

import yaml
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from tests.utils.cert import (
    astronomer_private_ca_cert_file,
    astronomer_tls_cert_file,
    astronomer_tls_key_file,
    create_astronomer_private_ca_certificates,
    create_astronomer_tls_certificates,
)
from tests.utils.install_ci_tools import install_all_tools

# Add the project root to the Python path so we can import test utilities
git_root_dir = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)

chart_metadata = yaml.safe_load((Path(git_root_dir) / "metadata.yaml").read_text())
kubectl_version = chart_metadata["test_k8s_versions"][-2]

DEBUG = os.getenv("DEBUG", "").lower() in ["yes", "true", "1"]

ScenarioType = Literal["unified", "data", "control"]

astronomer_software_dir = Path.home() / ".local" / "share" / "astronomer-software"
(astronomer_software_dir / "bin").mkdir(parents=True, exist_ok=True)
(astronomer_software_dir / "kubeconfig").mkdir(parents=True, exist_ok=True)
(astronomer_software_dir / "certs").mkdir(parents=True, exist_ok=True)

kind_exe = astronomer_software_dir / "bin" / "kind"
helm_exe = astronomer_software_dir / "bin" / "helm"
kubeconfig_dir = astronomer_software_dir / "kubeconfig"


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


def wait_for_pods_ready(kubeconfig_file: str, timeout: int = 300) -> None:
    """
    Wait until all pods in the cluster are in the 'Running' state.

    Args:
        kubeconfig_file: Path to the kubeconfig file.
        timeout: Maximum time (in seconds) to wait for all pods to be ready.

    Raises:
        RuntimeError: If not all pods are ready within the timeout.
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


def create_kind_cluster(cluster_name: str) -> PosixPath:
    """
    Create a KIND cluster and return its kubeconfig file path.

    Args:
        cluster_name: Name of the KIND cluster to create.

    Returns:
        Full path to the kubeconfig file.

    Raises:
        RuntimeError: If the cluster creation fails.
    """
    kubeconfig_file = kubeconfig_dir / f"{cluster_name}"
    kubeconfig_file.parent.mkdir(parents=True, exist_ok=True)
    kubeconfig_file.unlink(missing_ok=True)

    try:
        cmd = [
            f"{kind_exe}",
            "create",
            "cluster",
            f"--name={cluster_name}",
            f"--kubeconfig={kubeconfig_file}",
            f"--config={git_root_dir}/bin/kind/calico-config.yaml",
            f"--image=kindest/node:v{kubectl_version}",
        ]
        print(f"Creating KIND cluster with command: {shlex.join(cmd)}")
        run_command(cmd)

        # Wait until all pods are ready
        print("Waiting for all pods to become ready...")
        wait_for_pods_ready(str(kubeconfig_file))

        # Apply calico configuration
        cmd = [
            "kubectl",
            f"--kubeconfig={kubeconfig_file}",
            "--namespace=kube-system",
            "apply",
            f"--filename={git_root_dir}/bin/kind/calico-crds-v{kubectl_version.rpartition('.')[0]}.yaml",
        ]
        print(f"Applying Calico configuration with command: {shlex.join(cmd)}")
        run_command(cmd)

        # Configure Calico to ignore loose reverse path filtering
        cmd = [
            "kubectl",
            f"--kubeconfig={kubeconfig_file}",
            "--namespace=kube-system",
            "set",
            "env",
            "daemonset/calico-node",
            "FELIX_IGNORELOOSERPF=true",
        ]
        print(f"Configuring Calico with command: {shlex.join(cmd)}")
        run_command(cmd)

        return kubeconfig_file
    except Exception:
        # Cleanup if cluster creation fails
        cmd = [f"{kind_exe}", "delete", "cluster", f"--name={cluster_name}"]
        print(f"Cleaning up after failed cluster creation with command: {shlex.join(cmd)}")
        run_command(cmd)
        kubeconfig_file.unlink(missing_ok=True)
        raise


def create_namespace(kubeconfig_file: str, namespace: str = "astronomer") -> None:
    """
    Create the given namespace.

    Args:
        kubeconfig_file: Path to the kubeconfig file.
        namespace: Name of the namespace to create.

    Raises:
        FileNotFoundError: If the kubeconfig file doesn't exist.
        RuntimeError: If namespace creation fails.
    """
    if not Path(kubeconfig_file).exists():
        raise FileNotFoundError(f"Kubeconfig file not found at {kubeconfig_file}")

    cmd = [
        "kubectl",
        f"--kubeconfig={kubeconfig_file}",
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


def create_astronomer_tls_secret(kubeconfig_file: str) -> None:
    """
    Create the astronomer-tls secret in the KIND cluster using self-signed certificates.

    Args:
        kubeconfig_file: Path to the kubeconfig file.

    Raises:
        FileNotFoundError: If the kubeconfig file doesn't exist.
        RuntimeError: If secret creation fails.
    """
    if not Path(kubeconfig_file).exists():
        raise FileNotFoundError(f"Kubeconfig file not found at {kubeconfig_file}")

    create_astronomer_tls_certificates()

    secret_name = "astronomer-tls"  # noqa: S105
    cmd = [
        "kubectl",
        f"--kubeconfig={kubeconfig_file}",
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


def create_private_ca_secret(kubeconfig_file: str) -> None:
    """
    Create the private-ca secret in the KIND cluster using self-signed certificates.

    Args:
        kubeconfig_file: Path to the kubeconfig file.

    Raises:
        FileNotFoundError: If the kubeconfig file doesn't exist.
        RuntimeError: If secret creation fails.
    """
    if not Path(kubeconfig_file).exists():
        raise FileNotFoundError(f"Kubeconfig file not found at {kubeconfig_file}")

    create_astronomer_private_ca_certificates()

    cmd = [
        "kubectl",
        f"--kubeconfig={kubeconfig_file}",
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


def setup_common_cluster_configs(kubeconfig_file: str) -> None:
    """
    Perform steps that are common to all installation scenarios.

    Args:
        kubeconfig_file: Path to the kubeconfig file.
    """
    create_namespace(kubeconfig_file)
    create_astronomer_tls_secret(kubeconfig_file)
    create_private_ca_secret(kubeconfig_file)


def kind_load_docker_images(cluster: str) -> None:
    """
    Load any available docker images into a KIND cluster.

    For any images found in CircleCI config that are also found in the local Docker cache,
    load images into the KIND cluster instead of downloading them from the Docker registry.
    This is useful for local development and testing.

    Args:
        cluster: Name of the KIND cluster to load images into.
    """
    circleci_config = yaml.safe_load((git_root_dir / ".circleci" / "config.yml").read_text())
    image_list = circleci_config["workflows"]["scan-docker-images"]["jobs"][1]["twistcli-scan-docker"]["matrix"]["parameters"][
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
        cmd = [f"{kind_exe}", "load", "docker-image", "--name", cluster, image]
        print(f"Loading Docker images into KIND cluster with command: {shlex.join(cmd)}")
        try:
            run_command(cmd)
        except RuntimeError as e:
            print(f"Failed to load image '{image}' into KIND cluster '{cluster}': {e}")
            continue


def helm_install(kubeconfig: str, values: str | list[str] = f"{git_root_dir}/configs/local-dev.yaml") -> None:
    """
    Install a Helm chart using the provided kubeconfig and values file.

    Args:
        kubeconfig: Path to the kubeconfig file.
        values: Path to the Helm values file or a list of values files.

    Raises:
        ValueError: If invalid values file is provided.
    """
    helm_install_command = [
        helm_exe,
        "install",
        "astronomer",
        "--create-namespace",
        "--namespace=astronomer",
        str(git_root_dir),
        f"--kubeconfig={kubeconfig}",
        "--timeout=15m0s",
    ]

    if isinstance(values, str):
        values = [values]

    for value in values:
        if isinstance(value, str) and Path(value).exists():
            helm_install_command.append(f"--values={value}")
        else:
            raise ValueError(f"Invalid values file: {value}")

    if DEBUG:
        helm_install_command.append("--debug")

    run_command(helm_install_command)


def delete_kind_cluster(cluster_name: str, kubeconfig_file: PosixPath) -> None:
    """
    Delete a KIND cluster and clean up its kubeconfig file.

    Args:
        cluster_name: Name of the KIND cluster to delete.
        kubeconfig_file: Path to the kubeconfig file to clean up.
    """
    try:
        cmd = [
            f"{kind_exe}",
            "delete",
            "cluster",
            f"--name={cluster_name}",
        ]
        print(f"Deleting KIND cluster with command: {shlex.join(cmd)}")
        run_command(cmd)
    finally:
        kubeconfig_file.unlink(missing_ok=True)


def setup_functional_test_environment(
    scenario: ScenarioType,
    cluster_name: str | None = None,
    values_files: list[str] | None = None,
    load_images: bool = True,
    cleanup_existing: bool = True,
) -> str:
    """
    Set up a complete functional test environment for the specified scenario.

    Args:
        scenario: The deployment scenario (unified, data, or control).
        cluster_name: Name of the KIND cluster (defaults to scenario name).
        values_files: List of Helm values files to use.
        load_images: Whether to load local Docker images into the cluster.
        cleanup_existing: Whether to clean up existing cluster before creating new one.

    Returns:
        Path to the kubeconfig file for the created cluster.
    """
    if cluster_name is None:
        cluster_name = scenario

    kubeconfig_file = kubeconfig_dir / cluster_name

    print(f"Setting up functional test environment for scenario: {scenario}")
    print(f"Cluster name: {cluster_name}")

    # Install required tools
    print("Installing required tools...")
    install_all_tools()

    # Clean up existing cluster if requested
    if cleanup_existing and kubeconfig_file.exists():
        print(f"Cleaning up existing cluster: {cluster_name}")
        delete_kind_cluster(cluster_name, kubeconfig_file)

    # Create KIND cluster
    print(f"Creating KIND cluster: {cluster_name}")
    kubeconfig_file = create_kind_cluster(cluster_name)

    # Load Docker images if requested
    if load_images:
        print("Loading local Docker images into cluster...")
        kind_load_docker_images(cluster_name)

    # Set up common cluster configurations
    print("Setting up common cluster configurations...")
    setup_common_cluster_configs(str(kubeconfig_file))

    # Install Astronomer software via Helm
    print("Installing Astronomer software via Helm...")
    if values_files is None:
        values_files = [f"{git_root_dir}/configs/local-dev.yaml"]
    helm_install(str(kubeconfig_file), values_files)

    print("Functional test environment setup complete!")
    print(f"Kubeconfig file: {kubeconfig_file}")
    print(f"To use this cluster, run: export KUBECONFIG={kubeconfig_file}")

    return str(kubeconfig_file)


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Setup functional test environment for Astronomer software testing")
    parser.add_argument(
        "scenario",
        choices=["unified", "data", "control"],
        help="Deployment scenario to set up",
    )
    parser.add_argument(
        "--cluster-name",
        help="Name of the KIND cluster (defaults to scenario name)",
    )
    parser.add_argument(
        "--values",
        action="append",
        help="Helm values file to use (can be specified multiple times)",
    )
    parser.add_argument(
        "--no-load-images",
        action="store_true",
        help="Skip loading local Docker images into the cluster",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Don't clean up existing cluster before creating new one",
    )
    parser.add_argument(
        "--delete-only",
        action="store_true",
        help="Only delete the specified cluster, don't create a new one",
    )

    args = parser.parse_args()

    cluster_name = args.cluster_name or args.scenario
    kubeconfig_file = kubeconfig_dir / cluster_name

    if args.delete_only:
        if kubeconfig_file.exists():
            print(f"Deleting cluster: {cluster_name}")
            delete_kind_cluster(cluster_name, kubeconfig_file)
            print("Cluster deleted successfully")
        else:
            print(f"Cluster {cluster_name} does not exist")
        return

    try:
        setup_functional_test_environment(
            scenario=args.scenario,
            cluster_name=args.cluster_name,
            values_files=args.values,
            load_images=not args.no_load_images,
            cleanup_existing=not args.no_cleanup,
        )
    except Exception as e:  # noqa: BLE001
        print(f"Error setting up functional test environment: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
