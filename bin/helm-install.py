#!/usr/bin/env python3
"""Install the current chart into the given cluster."""

import argparse
import datetime
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

GIT_ROOT_DIR = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)
HELPER_BIN_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "bin"
KUBECTL_EXE = str(HELPER_BIN_DIR / "kubectl")
HELM_EXE = str(HELPER_BIN_DIR / "helm")
HELM_INSTALL_TIMEOUT = os.getenv("HELM_INSTALL_TIMEOUT", "10m0s")
KUBECONFIG_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "kubeconfig"
KUBECONFIG_DIR.mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed command line arguments.
    """
    parser = argparse.ArgumentParser(description="Install the current chart into the given cluster.")
    parser.add_argument(
        "--topology",
        required=True,
        choices=["unified", "control", "data"],
        help="Install topology: unified (control+data in one cluster), control, or data.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (can also be set via DEBUG environment variable)")
    parser.add_argument(
        "--helm-values",
        action="append",
        default=[],
        dest="helm_values",
        metavar="FILE",
        help="Extra Helm values file, relative to the repo root unless absolute (can be repeated).",
    )
    parser.add_argument(
        "--namespace-label",
        action="append",
        default=[],
        dest="namespace_labels",
        metavar="KEY=VALUE",
        help="Label to apply to the astronomer namespace before install (can be repeated). "
        "Creates the namespace ahead of `helm install` instead of using --create-namespace, "
        "since PSA enforcement labels must be present before pods are created.",
    )
    return parser.parse_args()


def debug_print(message: str) -> None:
    """
    Print a debug message if DEBUG mode is enabled.

    Args:
        message: The debug message to print.
    """
    if DEBUG:
        print(f"DEBUG: {message}")


def date_print(*args):
    """print() with a TZ aware iso8601 date prefixed."""
    print(datetime.datetime.now(datetime.UTC).isoformat(), *args)


def show_failing_pod_logs(tail: int = 100):
    """
    Print logs from all containers in failing states, including initContainers, excluding those where logs are not possible.
    :param tail: Number of log lines to show per container
    """
    date_print("Failing pod logs are shown below:")
    exclude_reasons = {
        "ContainerCreating",
        # "CreateContainerConfigError",
        # "CreateContainerError",
        # "ErrImagePull",
        # "ImageInspectError",
        # "ImagePullBackOff",
        # "InvalidImageName",
        "PodInitializing",
    }
    get_pods_cmd = [
        KUBECTL_EXE,
        f"--kubeconfig={KUBECONFIG_FILE}",
        "get",
        "pods",
        "--namespace=astronomer",
        "--output=json",
    ]
    try:
        pods_json = subprocess.check_output(get_pods_cmd)
    except subprocess.CalledProcessError as e:
        print(f"Failed to get pods: {e}")
        return
    pods = json.loads(pods_json)
    for pod in pods.get("items", []):
        pod_name = pod["metadata"]["name"]
        all_statuses = pod.get("status", {}).get("containerStatuses", []) + pod.get("status", {}).get("initContainerStatuses", [])
        for cs in all_statuses:
            state = cs.get("state", {})
            if waiting := state.get("waiting"):
                reason = waiting.get("reason")
                if reason in exclude_reasons:
                    continue
                container_name = cs["name"]
                print(f"=== {pod_name}/{container_name} ({reason}) ===")
                logs_cmd = [
                    KUBECTL_EXE,
                    f"--kubeconfig={KUBECONFIG_FILE}",
                    "logs",
                    "--namespace=astronomer",
                    pod_name,
                    "-c",
                    container_name,
                    f"--tail={tail}",
                ]
                try:
                    logs = subprocess.check_output(logs_cmd, stderr=subprocess.STDOUT)
                    print(logs.decode())
                except subprocess.CalledProcessError as e:
                    print(f"Error getting logs: {e.output.decode()}")
                print()


def run_and_monitor_subprocess(command: list, monitor_function: callable, interval: int = 30):
    """
    Runs command in background and calls monitor_function() every `interval` seconds
    until the process completes.
    """
    proc = subprocess.Popen(command)
    try:
        while proc.poll() is None:
            monitor_function()
            time.sleep(interval)
    finally:
        proc.wait()


def create_and_label_namespace(labels: dict[str, str], namespace: str = "astronomer") -> None:
    """
    Create a namespace and apply labels to it before anything is installed into it.

    Pod Security Admission is enforced at pod-creation time, not retroactively, so labels
    meant to trigger enforcement (e.g. pod-security.kubernetes.io/enforce) must land before
    `helm install` creates any pods -- `helm install --create-namespace` applies no labels.

    :param labels: Namespace labels to apply, e.g. {"pod-security.kubernetes.io/enforce": "restricted"}.
    :param namespace: Namespace name to create and label.
    """
    debug_print(f"Creating namespace {namespace} with labels: {labels}")
    result = subprocess.run(
        [KUBECTL_EXE, f"--kubeconfig={KUBECONFIG_FILE}", "create", "namespace", namespace],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "AlreadyExists" not in result.stderr:
        raise RuntimeError(f"Failed to create namespace {namespace}: {result.stderr}")

    label_args = [f"{key}={value}" for key, value in labels.items()]
    subprocess.run(
        [KUBECTL_EXE, f"--kubeconfig={KUBECONFIG_FILE}", "label", "namespace", namespace, *label_args, "--overwrite"],
        check=True,
    )


def helm_install(
    values: str | list[str] = f"{GIT_ROOT_DIR}/configs/local-dev.yaml",
    create_namespace: bool = True,
) -> None:
    """
    Install a Helm chart using the provided kubeconfig and values file.

    :param values: Path to the Helm values file or a list of values files.
    :param create_namespace: Pass --create-namespace to helm. Set False when the namespace
        was already created (and labeled) ahead of install via create_and_label_namespace().
    """
    debug_print(f"Starting Helm install with values: {values}")
    debug_print(f"Using kubeconfig: {KUBECONFIG_FILE}")
    debug_print(f"Helm timeout: {HELM_INSTALL_TIMEOUT}")

    helm_install_command = [
        HELM_EXE,
        "install",
        "astronomer",
        str(GIT_ROOT_DIR),
        "--namespace=astronomer",
        f"--timeout={HELM_INSTALL_TIMEOUT}",
        f"--kubeconfig={KUBECONFIG_FILE}",
    ]
    if create_namespace:
        helm_install_command.append("--create-namespace")

    if isinstance(values, str):
        values = [values]

    for value in values:
        if isinstance(value, str) and Path(value).exists():
            helm_install_command.append(f"--values={value}")
            debug_print(f"Added values file: {value}")
        else:
            raise ValueError(f"Invalid values file: {value}")

    debug_print(f"Final Helm command: {shlex.join(helm_install_command)}")

    try:
        run_and_monitor_subprocess(helm_install_command, show_failing_pod_logs, interval=30)
    except (RuntimeError, subprocess.CalledProcessError) as e:
        debug_print(f"Helm install failed: {e}")
        show_pod_status()
        show_failing_pod_logs()
        print("Helm install failed. Please check the logs above for details.", file=sys.stderr)
        raise

    debug_print("Helm install completed successfully")


def show_pod_status() -> None:
    """Print the status of all pods in the specified namespace."""
    print("Current astronomer namespace pod status:")
    pod_status = subprocess.check_output(
        [
            KUBECTL_EXE,
            f"--kubeconfig={KUBECONFIG_FILE}",
            "--namespace=astronomer",
            "get",
            "pods",
            "-o",
            "wide",
        ],
        text=True,
    )
    print(pod_status)


def wait_for_healthy_pods(ignore_substrings: list[str] | None = None, max_wait_time=120) -> None:
    """
    Wait for all pods in the 'astronomer' namespace to be in a healthy state.
    """
    debug_print(f"Starting pod health check with max wait time: {max_wait_time}s")
    if ignore_substrings:
        debug_print(f"Ignoring pods containing: {ignore_substrings}")
    print("Waiting for pods in the 'astronomer' namespace to be healthy...")
    end_time = time.time() + max_wait_time
    while True:
        debug_print(f"Checking pod status... {int(end_time - time.time())}s remaining")

        output = subprocess.run(
            [
                KUBECTL_EXE,
                f"--kubeconfig={KUBECONFIG_FILE}",
                "--namespace=astronomer",
                "get",
                "pods",
                "-o",
                "custom-columns=NAME:.metadata.name,STATUS:.status.phase,OWNER:.metadata.ownerReferences[0].kind",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        if time.time() >= end_time:
            err = "Timeout waiting for pods to become healthy."
            print(output)
            raise RuntimeError(err)
        lines = output.stdout.splitlines()[1:]  # Skip the header line
        unhealthy_pods = []
        for line in lines:
            parts = line.split()
            if len(parts) < 3:
                continue
            name, status, owner_kind = parts[0], parts[1], parts[2]
            if status == "Failed" and owner_kind == "Job":
                debug_print(f"Ignoring failed Job pod: {name}")
                continue
            if status not in ["Running", "Succeeded"]:
                unhealthy_pods.append(name)
                if ignore_substrings and any(substring in name for substring in ignore_substrings):
                    debug_print(f"Ignoring unhealthy pod: {name} (status: {status})")
                    continue
        if not unhealthy_pods:
            debug_print("All pods are healthy, exiting wait loop")
            print("All pods in the 'astronomer' namespace are healthy.")
            show_pod_status()
            return
        date_print(f"Found {len(unhealthy_pods)} unhealthy pods: {', '.join(unhealthy_pods)}")
        show_pod_status()
        time.sleep(5)

        print(f"Retrying... {int(end_time - time.time())} seconds left until timeout.")


if __name__ == "__main__":
    args = parse_args()
    TOPOLOGY = args.topology
    KUBECONFIG_FILE = str(KUBECONFIG_DIR / TOPOLOGY)

    # Set DEBUG based on command line argument or environment variable
    DEBUG = args.debug or os.getenv("DEBUG", "").lower() in ["yes", "true", "1"]

    debug_print("Debug mode enabled")
    debug_print(f"{TOPOLOGY=}")
    debug_print(f"{GIT_ROOT_DIR=}")
    debug_print(f"{KUBECONFIG_FILE=}")
    debug_print(f"{KUBECTL_EXE=}")
    debug_print(f"{HELM_EXE=}")
    debug_print(f"{HELM_INSTALL_TIMEOUT=}")

    values = [
        f"{GIT_ROOT_DIR}/configs/local-dev.yaml",
        f"{GIT_ROOT_DIR}/tests/data_files/scenario-{TOPOLOGY}.yaml",
    ]
    for extra_values_file in args.helm_values:
        path = Path(extra_values_file)
        values.append(str(path if path.is_absolute() else GIT_ROOT_DIR / path))

    debug_print(f"Preparing to install with values files: {values}")
    for value_file in values:
        if Path(value_file).exists():
            debug_print(f"Values file exists: {value_file}")
        else:
            debug_print(f"WARNING - Values file not found: {value_file}")

    namespace_labels = dict(kv.split("=", 1) for kv in args.namespace_labels)
    if namespace_labels:
        create_and_label_namespace(namespace_labels)
    helm_install(values=values, create_namespace=not namespace_labels)
    wait_for_healthy_pods()
