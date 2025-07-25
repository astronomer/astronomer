#!/usr/bin/env python3
"""Install the current chart into the given cluster."""

import argparse
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

    debug_print(f"Executing command: {command}")

    result = subprocess.run(command, shell=True, text=True, capture_output=True)

    debug_print(f"Command exit code: {result.returncode}")
    if stdout := result.stdout.strip():
        debug_print(f"Command stdout: {stdout}")
    if stderr := result.stderr.strip():
        debug_print(f"Command stderr: {stderr}")

    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {command}\n{result.stderr}")
    return result.stdout.strip()


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
        "--debug",
        "--create-namespace",
        "--namespace=astronomer",
        str(GIT_ROOT_DIR),
        f"--kubeconfig={KUBECONFIG_FILE}",
        f"--timeout={HELM_INSTALL_TIMEOUT}",
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

    run_command(helm_install_command)

    debug_print("Helm install completed successfully")


def wait_for_healthy_pods(ignore_substrings: list[str] | None = None, max_wait_time=90) -> None:
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

        output = run_command(
            [
                KUBECTL_EXE,
                "--kubeconfig",
                KUBECONFIG_FILE,
                "get",
                "pods",
                "--namespace=astronomer",
                "-o",
                "custom-columns=NAME:.metadata.name,STATUS:.status.phase",
            ]
        )
        if time.time() >= end_time:
            err = "Timeout waiting for pods to become healthy."
            print(output)
            raise RuntimeError(err)
        lines = output.splitlines()[1:]  # Skip the header line
        unhealthy_pods = []
        for line in lines:
            name, status = line.split()
            if status not in ["Running", "Succeeded"]:
                unhealthy_pods.append(name)
                if ignore_substrings and any(substring in name for substring in ignore_substrings):
                    debug_print(f"Ignoring unhealthy pod: {name} (status: {status})")
                    continue
        if not unhealthy_pods:
            debug_print("All pods are healthy, exiting wait loop")
            print("All pods in the 'astronomer' namespace are healthy.")
            return

        debug_print(f"Found {len(unhealthy_pods)} unhealthy pods")

        print(f"Unhealthy pods: {', '.join(unhealthy_pods)}")
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
