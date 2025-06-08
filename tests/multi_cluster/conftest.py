import os
import shlex
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path, PosixPath

import pytest
import testinfra
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from tests import git_root_dir, kubectl_version
from tests.utils.cert import (
    astronomer_private_ca_cert_file,
    astronomer_tls_cert_file,
    astronomer_tls_key_file,
    create_astronomer_private_ca_certificates,
    create_astronomer_tls_certificates,
)
from tests.utils.install_ci_tools import install_all_tools

DEBUG = os.getenv("DEBUG", "").lower() in ["yes", "true", "1"]


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

    :param command: The shell command to execute.
    :return: The standard output from the command.
    :raises RuntimeError: If the command fails.
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


def create_kind_cluster(cluster_name: str) -> PosixPath:
    """
    Create a KIND cluster and return its kubeconfig file path.

    :param cluster_name: Name of the KIND cluster to create.
    :return: Full path to the kubeconfig file.
    :raises RuntimeError: If the cluster creation fails.
    """
    # TODO: make kind load any containers that are found in the local docker cache (network optimization)
    kubeconfig_file = kubeconfig_dir / f"{cluster_name}"
    kubeconfig_file.parent.mkdir(parents=True, exist_ok=True)
    kubeconfig_file.unlink(missing_ok=True)
    install_all_tools()

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


def setup_common_cluster_configs(kubeconfig_file):
    """Perform steps that are common to all installation scenarios."""
    create_astronomer_tls_secret(kubeconfig_file)
    create_private_ca_secret(kubeconfig_file)


def delete_kind_cluster(cluster_name: str, kubeconfig_file: PosixPath) -> None:
    """
    Delete a KIND cluster and clean up its kubeconfig file.

    :param cluster_name: Name of the KIND cluster to delete.
    :param kubeconfig_file: Path to the kubeconfig file to clean up.
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


@pytest.fixture(scope="session")
def control(request) -> Iterable[str]:
    """
    Fixture for the 'control' cluster.

    :param request: Pytest request object for accessing test metadata.
    :yield: Path to the kubeconfig file for the 'control' cluster.
    """
    kubeconfig_file = create_kind_cluster("control")
    create_namespace(kubeconfig_file)
    setup_common_cluster_configs(kubeconfig_file)
    helm_install(
        kubeconfig=kubeconfig_file,
        values=[
            f"{git_root_dir}/configs/local-dev.yaml",
            f"{git_root_dir}/tests/data_files/scenario-controlplane.yaml",
        ],
    )
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
    setup_common_cluster_configs(kubeconfig_file)
    helm_install(
        kubeconfig=kubeconfig_file,
        values=[
            f"{git_root_dir}/configs/local-dev.yaml",
            f"{git_root_dir}/tests/data_files/scenario-dataplane.yaml",
        ],
    )
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
    setup_common_cluster_configs(kubeconfig_file)
    helm_install(
        kubeconfig=kubeconfig_file,
        values=[
            f"{git_root_dir}/configs/local-dev.yaml",
            f"{git_root_dir}/tests/data_files/scenario-unified.yaml",
        ],
    )
    yield kubeconfig_file
    delete_kind_cluster("unified", kubeconfig_file)


def helm_install(kubeconfig: str, values: str | list[str] = f"{git_root_dir}/configs/local-dev.yaml") -> None:
    """
    Install a Helm chart using the provided kubeconfig and values file.

    :param kubeconfig: Path to the kubeconfig file.
    :param values: Path to the Helm values file or a list of values files.
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


@pytest.fixture(scope="function")
def k8s_core_v1_client(request) -> client.CoreV1Api:
    """
    Provide a Kubernetes core/v1 client for the resolved target cluster.

    :param request: Pytest request object for accessing test metadata.
    :return: A Kubernetes CoreV1Api client for the target cluster.
    """
    cluster_name = request.param
    kubeconfig_file = kubeconfig_dir / f"{cluster_name}"
    config.load_kube_config(config_file=kubeconfig_file)
    return client.CoreV1Api()


@pytest.fixture(scope="function")
def k8s_apps_v1_client(request) -> client.AppsV1Api:
    """
    Provide a Kubernetes apps/v1 client for the resolved target cluster.

    :param request: Pytest request object for accessing test metadata.
    :return: A Kubernetes AppsV1Api client for the target cluster.
    """
    cluster_name = request.param
    kubeconfig_file = kubeconfig_dir / f"{cluster_name}"
    config.load_kube_config(config_file=kubeconfig_file)
    return client.AppsV1Api()


def create_namespace(kubeconfig_file, namespace="astronomer") -> None:
    """Create the given namespace."""
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


def create_astronomer_tls_secret(kubeconfig_file) -> None:
    """Create the astronomer-tls secret in the KIND cluster using self-signed certificates."""
    if not Path(kubeconfig_file).exists():
        raise FileNotFoundError(f"Kubeconfig file not found at {kubeconfig_file}")

    create_astronomer_tls_certificates()

    secret_name = "astronomer-tls"
    namespace = "astronomer"
    cmd = [
        "kubectl",
        f"--kubeconfig={kubeconfig_file}",
        f"--namespace={namespace}",
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
        raise RuntimeError(f"Failed to create secret {secret_name} in namespace {namespace}: {result.stderr}")


def create_private_ca_secret(kubeconfig_file) -> None:
    """Create the private-ca secret in the KIND cluster using self-signed certificates."""
    if not Path(kubeconfig_file).exists():
        raise FileNotFoundError(f"Kubeconfig file not found at {kubeconfig_file}")

    create_astronomer_private_ca_certificates()

    namespace = "astronomer"
    cmd = [
        "kubectl",
        f"--kubeconfig={kubeconfig_file}",
        f"--namespace={namespace}",
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
        raise RuntimeError(f"Failed to create secret private-ca in namespace {namespace}: {result.stderr}")


def check_pod_health(v1: client.CoreV1Api, namespace: str = "astronomer") -> tuple[bool, str]:
    """
    Check the health of all pods in the given namespace.

    Args:
        v1: Kubernetes CoreV1Api client
        namespace: Namespace to check pods

    Returns:
        tuple: (is_healthy, message)
    """
    try:
        pods = v1.list_namespaced_pod(namespace=namespace)
        unhealthy_pods = []

        for pod in pods.items:
            if pod.status.phase not in ["Running", "Succeeded"]:
                unhealthy_pods.append(f"{pod.metadata.name} (Phase: {pod.status.phase})")
                continue

            # Check container statuses
            for container in pod.status.container_statuses or []:
                if not container.ready:
                    restart_count = container.restart_count
                    state = next(iter(container.state.to_dict().keys()))
                    unhealthy_pods.append(
                        f"{pod.metadata.name}/{container.name} (Not Ready, State: {state}, Restarts: {restart_count})"
                    )

        if unhealthy_pods:
            return False, f"Unhealthy pods found: {', '.join(unhealthy_pods)}"
        return True, "All pods are healthy"

    except Exception as e:  # noqa: BLE001
        return False, f"Failed to check pod health: {e}"


def check_service_health(v1: client.CoreV1Api, namespace: str = "astronomer") -> tuple[bool, str]:
    """
    Check if all services have endpoints.

    Args:
        v1: Kubernetes CoreV1Api client
        namespace: Namespace to check services in

    Returns:
        tuple: (is_healthy, message)
    """
    try:
        services = v1.list_namespaced_service(namespace=namespace)
        endpoints = v1.list_namespaced_endpoints(namespace=namespace)

        services_without_endpoints = []
        for svc in services.items:
            # Skip headless services and kubernetes service
            if svc.spec.cluster_ip == "None" or svc.metadata.name == "kubernetes":
                continue

            has_endpoints = any(ep.metadata.name == svc.metadata.name and ep.subsets for ep in endpoints.items)
            if not has_endpoints:
                services_without_endpoints.append(svc.metadata.name)

        if services_without_endpoints:
            return False, f"Services without endpoints: {', '.join(services_without_endpoints)}"
        return True, "All services have endpoints"

    except Exception as e:  # noqa: BLE001
        return False, f"Failed to check service health: {e}"


def check_deployment_health(apps_v1: client.AppsV1Api, namespace: str = "astronomer") -> tuple[bool, str]:
    """
    Check if all deployments are at desired replica count.

    Args:
        apps_v1: Kubernetes AppsV1Api client
        namespace: Namespace to check deployments in

    Returns:
        tuple: (is_healthy, message)
    """
    try:
        deployments = apps_v1.list_namespaced_deployment(namespace=namespace)
        unhealthy_deployments = []

        unhealthy_deployments.extend(
            f"{deployment.metadata.name} (Ready: {deployment.status.ready_replicas or 0}/{deployment.spec.replicas})"
            for deployment in deployments.items
            if deployment.status.ready_replicas != deployment.spec.replicas
        )
        if unhealthy_deployments:
            return False, f"Unhealthy deployments found: {', '.join(unhealthy_deployments)}"
        return True, "All deployments are healthy"

    except Exception as e:  # noqa: BLE001
        return False, f"Failed to check deployment health: {e}"


def get_k8s_container_handle(*, pod_type, container, namespace, release_name):
    """Get a kubernetes container handle for a specific pod type and container."""
    pod = f"{release_name}-{pod_type}-0"
    return testinfra.get_host(f"kubectl://{pod}?container={container}&namespace={namespace}")
