#!/usr/bin/env python3

from os import getenv
import yaml
from subprocess import check_output
from packaging.version import parse as semver
from pytest import mark
from pathlib import Path

# The top-level path of this repository
git_root_dir = Path(
    check_output(["git", "rev-parse", "--show-toplevel"]).decode("utf-8").rstrip()
)


def test_astro_sub_chart_version_match():
    """Tests that Chart.yaml and charts/astronomer/Chart.yaml have matching
    versions."""
    with open(git_root_dir / "Chart.yaml") as f:
        astro_chart_dot_yaml = yaml.safe_load(f.read())

    with open(git_root_dir / "charts" / "astronomer" / "Chart.yaml") as f:
        astro_subchart_dot_yaml = yaml.safe_load(f.read())
    assert astro_chart_dot_yaml["version"] == astro_subchart_dot_yaml["version"], (
        "Please ensure that 'version' in Chart.yaml and "
        + "charts/astronomer/Chart.yaml exactly match."
    )


@mark.skip(reason="https://github.com/astronomer/issues/issues/2486")
def test_downgrade_then_upgrade():
    """If the patch version is greater than zero, check that we can perform a
    version downgrade, followed by version upgrade back to the current
    version."""
    helm_chart_path = getenv("HELM_CHART_PATH")
    if not helm_chart_path:
        raise Exception(
            "This test only works with HELM_CHART_PATH set to the path of the chart to be tested"
        )
    with open(git_root_dir / "Chart.yaml") as f:
        astro_chart_dot_yaml = yaml.safe_load(f.read())
    major, minor, patch = semver(astro_chart_dot_yaml["version"]).release
    if patch == 0:
        print("This test is not applicable to patch version 0")
        return

    if not (namespace := getenv("NAMESPACE")):
        print("NAMESPACE env var is not present, using 'astronomer' namespace")
        namespace = "astronomer"

    if not (release_name := getenv("RELEASE_NAME")):
        print("No RELEASE_NAME env var, usgin RELEASE_NAME=astronomer")
        release_name = "astronomer"

    config_path = git_root_dir / "upgrade_test_config.yaml"
    # Get the existing values
    check_output(
        f"helm get values -n {namespace} {release_name} > {config_path}", shell=True
    )
    # attempt downgrade with the documented procedure
    print("Performing patch version downgrade...")
    command = (
        "helm upgrade --reset-values "
        + f"-f {config_path} "
        + f"-n {namespace} "
        + f"--version={major}.{minor}.{patch - 1} "
        + f"{release_name} "
        + "astronomer-internal/astronomer"
    )
    print(command)
    print(check_output(command, shell=True))
    print("The downgrade worked, upgrading!")
    command = (
        "helm upgrade --reset-values "
        + f"-f {config_path} "
        + f"-n {namespace} "
        + f"--version={major}.{minor}.{patch} "
        + f"{release_name} "
        + helm_chart_path
    )
    print(command)
    print(check_output(command, shell=True))
    print("The upgrade worked!")
