#!/usr/bin/env python3
"""Install the current chart into the given cluster."""

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


def helm_install(values: str | list[str] = f"{GIT_ROOT_DIR}/configs/local-dev.yaml") -> None:
    """
    Install a Helm chart using the provided kubeconfig and values file.

    :param values: Path to the Helm values file or a list of values files.
    """
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
        else:
            raise ValueError(f"Invalid values file: {value}")

    run_command(helm_install_command)


def wait_for_healthy_pods(ignore_substrings: list[str] | None = None, max_wait_time=90) -> None:
    """
    Wait for all pods in the 'astronomer' namespace to be in a healthy state.
    """
    print("Waiting for pods to be healthy...")
    end_time = time.time() + max_wait_time

    while True:
        if time.time() >= end_time:
            raise RuntimeError("Timeout waiting for pods to become healthy.")
        output = run_command(
            [
                KUBECTL_EXE,
                "--kubeconfig",
                KUBECONFIG_FILE,
                "get",
                "pods",
                "--namespace=astronomer",
                "-o",
                'custom-columns="NAME:.metadata.name,STATUS:.status.phase"',
            ]
        )
        lines = output.splitlines()[1:]  # Skip the header line
        unhealthy_pods = []
        for line in lines:
            name, status = line.split()
            if status not in ["Running", "Succeeded"]:
                unhealthy_pods.append(name)
                if ignore_substrings and any(substring in name for substring in ignore_substrings):
                    continue
        if not unhealthy_pods:
            print("All pods are healthy.")
            return
        print(f"Unhealthy pods: {', '.join(unhealthy_pods)}")
        time.sleep(5)

        print(f"Retrying... {int(end_time - time.time())} seconds left until timeout.")


if __name__ == "__main__":
    values = [
        f"{GIT_ROOT_DIR}/configs/local-dev.yaml",
        f"{GIT_ROOT_DIR}/tests/data_files/scenario-{TEST_SCENARIO}.yaml",
    ]
    helm_install(values=values)
    wait_for_healthy_pods()
