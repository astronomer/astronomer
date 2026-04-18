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
