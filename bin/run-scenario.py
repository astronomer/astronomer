#!/usr/bin/env python3
"""Run a named test scenario from tests/functional/scenarios/<name>/test_profile.yaml.

A scenario composes an existing install topology (unified/control/data) with extra
values overlays, an optional pinned k8s version, and optional namespace labels applied
before install. See tests/functional/scenarios/README.md for the manifest format.
"""

import argparse
import os
import shlex
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

GIT_ROOT_DIR = next((p for p in Path(__file__).resolve().parents if (p / ".git").exists()), None)
if GIT_ROOT_DIR is None:
    raise SystemExit(f"ERROR: could not locate the repository root: no .git entry found above {Path(__file__).resolve()}")
SCENARIOS_DIR = GIT_ROOT_DIR / "tests" / "functional" / "scenarios"
CHART_METADATA = yaml.safe_load((GIT_ROOT_DIR / "metadata.yaml").read_text())


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "scenario",
        nargs="?",
        help="Scenario name, e.g. auth-sidecar (a tests/functional/scenarios/<name>/test_profile.yaml). "
        "Omit to list the available scenarios and their descriptions.",
    )
    return parser.parse_args()


def discover_scenarios() -> list[tuple[str, str]]:
    """(name, description) for every tests/functional/scenarios/<name>/test_profile.yaml, name-sorted."""
    scenarios = []
    for profile_path in sorted(SCENARIOS_DIR.glob("*/test_profile.yaml")):
        try:
            profile = yaml.safe_load(profile_path.read_text()) or {}
            description = (profile.get("description") or "").strip() or "(no description set)"
        except yaml.YAMLError as exc:
            description = f"(could not parse manifest: {exc})"
        scenarios.append((profile_path.parent.name, description))
    return scenarios


def print_scenarios() -> None:
    """List the available scenarios and their descriptions -- what running with no argument prints."""
    scenarios = discover_scenarios()
    if not scenarios:
        print(f"No scenarios found under {SCENARIOS_DIR}", file=sys.stderr)
        return
    print("Available scenarios:\n")
    for name, description in scenarios:
        print(f"  {name}")
        print(textwrap.fill(description, width=96, initial_indent="      ", subsequent_indent="      "))
        print()
    print(f"Run one with: {Path(__file__).name} <scenario>")


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
    if not args.scenario:
        print_scenarios()
        return
    profile = load_profile(args.scenario)
    kube_version = resolve_kube_version(profile)

    env = os.environ.copy()
    env["KUBE_VERSION"] = f"v{kube_version}"

    reset_local_dev_args = [f"--topology={profile['topology']}"]
    reset_local_dev_args += [f"--helm-values={value_file}" for value_file in profile["values"]]
    for key, value in profile.get("namespace_labels", {}).items():
        reset_local_dev_args.append(f"--namespace-label={key}={value}")
    # Scenario setup that must run after the cluster exists but before `helm install`
    # (e.g. creating a Secret the chart's install-time values reference). Forwarded to
    # reset-local-dev, which runs each between setup-kind.py and helm-install.py.
    for entry in profile.get("pre_helm_scripts", []):
        # Each entry is a repo-relative script path, optionally followed by arguments, e.g.
        # "bin/setup-forgejo-ca.py --platform-namespace astronomer --forgejo-namespace git-forgejo".
        tokens = shlex.split(entry)
        script_path = (GIT_ROOT_DIR / tokens[0]).resolve()
        if not script_path.exists():
            raise SystemExit(f"ERROR: pre_helm_scripts entry not found: {script_path}")
        reset_local_dev_args.append(f"--pre-helm-script={shlex.join([str(script_path), *tokens[1:]])}")

    command = [str(GIT_ROOT_DIR / "bin" / "reset-local-dev"), *reset_local_dev_args]
    print(f"Running scenario {args.scenario!r}: topology={profile['topology']} kube_version={kube_version}")
    if profile.get("description"):
        print(profile["description"].strip())
    print(f"Command: {command}")
    subprocess.run(command, env=env, cwd=GIT_ROOT_DIR, check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: scenario setup failed: {e}", file=sys.stderr)
        raise SystemExit(1) from e
