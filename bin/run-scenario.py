#!/usr/bin/env python3
"""Run a named test scenario from tests/functional/scenarios/<name>/test_profile.yaml.

A scenario composes an existing install topology (unified/control/data) with extra
values overlays, an optional pinned k8s version, and optional namespace labels applied
before install. See tests/functional/scenarios/README.md for the manifest format.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

GIT_ROOT_DIR = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)
SCENARIOS_DIR = GIT_ROOT_DIR / "tests" / "functional" / "scenarios"
CHART_METADATA = yaml.safe_load((GIT_ROOT_DIR / "metadata.yaml").read_text())


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario", help="Scenario name, e.g. auth-sidecar (must have a tests/functional/scenarios/<name>/test_profile.yaml)"
    )
    return parser.parse_args()


def load_profile(scenario: str) -> dict:
    """Load and validate a scenario's test_profile.yaml."""
    profile_path = SCENARIOS_DIR / scenario / "test_profile.yaml"
    if not profile_path.exists():
        raise SystemExit(f"ERROR: no such scenario manifest: {profile_path}")
    profile = yaml.safe_load(profile_path.read_text())

    if profile.get("topology") not in ["unified", "control", "data"]:
        raise SystemExit(f"ERROR: {profile_path} must set topology to one of unified/control/data, got {profile.get('topology')!r}")
    if profile.get("values") is None:
        raise SystemExit(f"ERROR: {profile_path} must set a 'values' key (an empty list is fine if no overlay is needed)")
    return profile


def resolve_kube_version(profile: dict) -> str:
    """Resolve the k8s version to test against: the manifest's own pin, or the latest tested version."""
    return profile.get("kube_version") or CHART_METADATA["test_k8s_versions"][-1]


def main() -> None:
    args = parse_args()
    profile = load_profile(args.scenario)
    kube_version = resolve_kube_version(profile)

    env = os.environ.copy()
    env["KUBE_VERSION"] = f"v{kube_version}"

    reset_local_dev_args = [f"--topology={profile['topology']}"]
    reset_local_dev_args += [f"--helm-values={value_file}" for value_file in profile["values"]]
    for key, value in profile.get("namespace_labels", {}).items():
        reset_local_dev_args.append(f"--namespace-label={key}={value}")

    command = [str(GIT_ROOT_DIR / "bin" / "reset-local-dev"), *reset_local_dev_args]
    print(f"Running scenario {args.scenario!r}: topology={profile['topology']} kube_version={kube_version}")
    print(f"Command: {command}")
    subprocess.run(command, env=env, cwd=GIT_ROOT_DIR, check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: scenario setup failed: {e}", file=sys.stderr)
        raise SystemExit(1) from e
