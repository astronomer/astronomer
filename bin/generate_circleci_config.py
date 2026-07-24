#!/usr/bin/env python3
"""Generate the CircleCI config."""

import datetime
from pathlib import Path

import yaml
from jinja2 import Template

git_root_dir = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)
metadata = yaml.safe_load((git_root_dir / "metadata.yaml").read_text())
kube_versions = metadata["test_k8s_versions"]
ci_runner_version = (datetime.datetime.now()).strftime("%Y-%m")


def discover_scenarios() -> list[dict]:
    """Find scenarios under tests/functional/scenarios/*/test_profile.yaml.

    The manifest file's presence is the signal, not bare directory presence, so a
    half-finished or stray directory can't silently create (or hide) a CI job. Each
    scenario's own test_profile.yaml may set an optional `resource_class` (any
    CircleCI machine-executor resource class, e.g. xlarge/2xlarge) to size that
    scenario's CI job independently -- most scenarios don't need more than the
    default, but one running multiple concurrent Airflow Deployments can exhaust it.
    """
    scenarios_dir = git_root_dir / "tests" / "functional" / "scenarios"
    if not scenarios_dir.is_dir():
        return []
    profile_paths = sorted(scenarios_dir.glob("*/test_profile.yaml"), key=lambda p: p.parent.name)
    scenarios = []
    for profile_path in profile_paths:
        profile = yaml.safe_load(profile_path.read_text()) or {}
        scenarios.append(
            {
                "name": profile_path.parent.name,
                "resource_class": profile.get("resource_class", "xlarge"),
            }
        )
    return scenarios


def main():
    """Render the Jinja2 template file."""
    for version in kube_versions:
        maj_min = version.rpartition(".")[0]
        if not Path(git_root_dir / "tests" / "kind" / f"calico-crds-v{maj_min}.yaml").exists():
            raise SystemExit(f"ERROR: calico-crds-v{maj_min}.yaml is required for for CircleCI to succeed but it does not exist!")
    config_file_template_path = git_root_dir / ".circleci" / "config.yml.j2"
    config_file_path = git_root_dir / ".circleci" / "config.yml"

    templated_file_content = config_file_template_path.read_text()
    template = Template(templated_file_content)
    config = template.render(
        ci_runner_version=ci_runner_version,
        kube_versions=kube_versions,
        scenarios=discover_scenarios(),
    )
    with open(config_file_path, "w") as circle_ci_config_file:
        warning_header = (
            "# Warning: automatically generated file\n"
            + "# Please edit config.yml.j2, and use the script generate_circleci_config.py\n"
        )
        circle_ci_config_file.write(warning_header)
        circle_ci_config_file.write(config)
        circle_ci_config_file.write("\n")


if __name__ == "__main__":
    main()
