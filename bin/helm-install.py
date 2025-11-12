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

PREREQUISITES = """You MUST set your environment variable TEST_SCENARIO to one of the following values:
- unified: Install with the unified application mode.
- data: Install the with the dataplane application mode.
- control: Install with the controlplane application mode.
"""

GIT_ROOT_DIR = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)
HELPER_BIN_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "bin"
KUBECTL_EXE = str(HELPER_BIN_DIR / "kubectl")
HELM_EXE = str(HELPER_BIN_DIR / "helm")
HELM_INSTALL_TIMEOUT = os.getenv("HELM_INSTALL_TIMEOUT", "10m0s")
if not all([(TEST_SCENARIO := os.getenv("TEST_SCENARIO")), TEST_SCENARIO in ["unified", "data", "control"]]):
    print("ERROR: TEST_SCENARIO environment variable is not set!", file=sys.stderr)
    print(PREREQUISITES, file=sys.stderr)
    raise SystemExit(1)
KUBECONFIG_DIR = Path.home() / ".local" / "share" / "astronomer-software" / "kubeconfig"
KUBECONFIG_DIR.mkdir(parents=True, exist_ok=True)
KUBECONFIG_FILE = str(KUBECONFIG_DIR / TEST_SCENARIO)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed command line arguments.
    """
    parser = argparse.ArgumentParser(description="Install the current chart into the given cluster.")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (can also be set via DEBUG environment variable)")
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


def helm_install(values: str | list[str] = f"{GIT_ROOT_DIR}/configs/local-dev.yaml") -> None:
    """
    Install a Helm chart using the provided kubeconfig and values file.

    :param values: Path to the Helm values file or a list of values files.
    """
    debug_print(f"Starting Helm install with values: {values}")
    debug_print(f"Using kubeconfig: {KUBECONFIG_FILE}")
    debug_print(f"Helm timeout: {HELM_INSTALL_TIMEOUT}")

    helm_install_command = [
        HELM_EXE,
        "install",
        "astronomer",
        str(GIT_ROOT_DIR),
        "--create-namespace",
        "--namespace=astronomer",
        f"--timeout={HELM_INSTALL_TIMEOUT}",
        f"--kubeconfig={KUBECONFIG_FILE}",
    ]

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


def wait_for_healthy_pods(ignore_substrings: list[str] | None = None, max_wait_time=300) -> None:
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
        time.sleep(5)

        print(f"Retrying... {int(end_time - time.time())} seconds left until timeout.")


if __name__ == "__main__":
    args = parse_args()

    # Set DEBUG based on command line argument or environment variable
    DEBUG = args.debug or os.getenv("DEBUG", "").lower() in ["yes", "true", "1"]

    debug_print("Debug mode enabled")
    debug_print(f"{TEST_SCENARIO=}")
    debug_print(f"{GIT_ROOT_DIR=}")
    debug_print(f"{KUBECONFIG_FILE=}")
    debug_print(f"{KUBECTL_EXE=}")
    debug_print(f"{HELM_EXE=}")
    debug_print(f"{HELM_INSTALL_TIMEOUT=}")

    values = [
        f"{GIT_ROOT_DIR}/configs/local-dev.yaml",
        f"{GIT_ROOT_DIR}/tests/data_files/scenario-{TEST_SCENARIO}.yaml",
    ]

    debug_print(f"Preparing to install with values files: {values}")
    for value_file in values:
        if Path(value_file).exists():
            debug_print(f"Values file exists: {value_file}")
        else:
            debug_print(f"WARNING - Values file not found: {value_file}")

    helm_install(values=values)
    wait_for_healthy_pods()
