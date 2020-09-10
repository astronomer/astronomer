#!/usr/bin/env python3

import os
import yaml

# The top-level path of this repository
git_root_dir = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "..","..")

def test_astro_sub_chart_version_match():
    """
    Tests that Chart.yaml and charts/astronomer/Chart.yaml
    have matching versions.
    """
    with open(os.path.join(git_root_dir,
                           "Chart.yaml"), "r") as f:
        astro_chart_dot_yaml = yaml.safe_load(f.read())

    with open(os.path.join(git_root_dir,
                           "charts",
                           "astronomer",
                           "Chart.yaml"), "r") as f:
        astro_subchart_dot_yaml = yaml.safe_load(f.read())
    assert astro_chart_dot_yaml['version'] == astro_subchart_dot_yaml['version'], \
        "Please ensure that 'version' in Chart.yaml and " + \
        "charts/astronomer/Chart.yaml exactly match."
