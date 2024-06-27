#!/usr/bin/env python3
"""This script is used to create the circle config file so that we can stay
DRY."""
import subprocess
from pathlib import Path
import yaml

from jinja2 import Template

git_root_dir = next(
    iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None
)
metadata = yaml.safe_load((git_root_dir / "metadata.yaml").read_text())
kube_versions = metadata["test_k8s_versions"]

# https://circleci.com/developer/machine/image/ubuntu-2204
machine_image_version = "ubuntu-2204:2024.05.1"
ci_runner_version = "2024-07"


def list_docker_images():
    command = f"{git_root_dir}/bin/show-docker-images.py --with-houston"
    docker_images_output = subprocess.check_output(command, shell=True)
    docker_image_list = [
        x.split()[1] for x in docker_images_output.decode("utf-8").strip().split("\n")
    ]

    return sorted(set(docker_image_list))


def main():
    """Render the Jinja2 template file."""
    for version in kube_versions:
        maj_min = version.rpartition(".")[0]
        if not Path(
            git_root_dir / "bin" / "kind" / f"calico-crds-v{maj_min}.yaml"
        ).exists():
            raise SystemExit(
                f"ERROR: calico-crds-v{maj_min}.yaml is required for for CircleCI to succeed but it does not exist!"
            )
    config_file_template_path = git_root_dir / ".circleci" / "config.yml.j2"
    config_file_path = git_root_dir / ".circleci" / "config.yml"

    docker_images = list_docker_images()

    templated_file_content = config_file_template_path.read_text()
    template = Template(templated_file_content)
    config = template.render(
        kube_versions=kube_versions,
        docker_images=docker_images,
        machine_image_version=machine_image_version,
        ci_runner_version=ci_runner_version,
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
