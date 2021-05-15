#!/usr/bin/env python3

import os
import yaml
from subprocess import check_output
from packaging.version import parse as semver
from pytest import mark

# The top-level path of this repository
git_root_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..")


def test_astro_sub_chart_version_match():
    """
    Tests that Chart.yaml and charts/astronomer/Chart.yaml
    have matching versions.
    """
    with open(os.path.join(git_root_dir, "Chart.yaml"), "r") as f:
        astro_chart_dot_yaml = yaml.safe_load(f.read())

    with open(
        os.path.join(git_root_dir, "charts", "astronomer", "Chart.yaml"), "r"
    ) as f:
        astro_subchart_dot_yaml = yaml.safe_load(f.read())
    assert astro_chart_dot_yaml["version"] == astro_subchart_dot_yaml["version"], (
        "Please ensure that 'version' in Chart.yaml and "
        + "charts/astronomer/Chart.yaml exactly match."
    )


@mark.skip(reason="https://github.com/astronomer/issues/issues/2486")
def test_downgrade_then_upgrade():
    """
    If the patch version is greater than zero,
    check that we can perform a version downgrade,
    followed by version upgrade back to the current version
    """
    helm_chart_path = os.environ.get("HELM_CHART_PATH")
    if not helm_chart_path:
        raise Exception(
            "This test only works with HELM_CHART_PATH set to the path of the chart to be tested"
        )
    with open(os.path.join(git_root_dir, "Chart.yaml"), "r") as f:
        astro_chart_dot_yaml = yaml.safe_load(f.read())
    major, minor, patch = semver(astro_chart_dot_yaml["version"]).release
    if patch == 0:
        print("This test is not applicable to patch version 0")
        return

    namespace = os.environ.get("NAMESPACE")
    release_name = os.environ.get("RELEASE_NAME")
    if not namespace:
        print("NAMESPACE env var is not present, using 'astronomer' namespace")
        namespace = "astronomer"
    if not release_name:
        print(
            "RELEASE_NAME env var is not present, assuming 'astronomer' is the release name"
        )
        release_name = "astronomer"

    config_path = os.path.join(git_root_dir, "upgrade_test_config.yaml")
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
