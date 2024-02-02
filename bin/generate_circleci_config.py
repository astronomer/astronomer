#!/usr/bin/env python3
"""This script is used to create the circle config file so that we can stay
DRY."""
import subprocess
from pathlib import Path
import yaml

from jinja2 import Template

GIT_ROOT = next(
    iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None
)
metadata = yaml.safe_load((GIT_ROOT / "metadata.yaml").read_text())
kube_versions = metadata["test_k8s_versions"]

# https://circleci.com/developer/machine/image/ubuntu-2204
machine_image_version = "ubuntu-2204:2023.07.2"
ci_runner_version = "2024-02"


def list_docker_images():
    command = f"cd {GIT_ROOT} && helm template . --set forceIncompatibleKubernetes=true -f tests/enable_all_features.yaml 2>/dev/null | awk '/image: / {{print $2}}' | sed 's/\"//g' | sort -u"
    docker_images_output = subprocess.check_output(command, shell=True)
    docker_image_list = docker_images_output.decode("utf-8").strip().split("\n")

    return sorted(set(docker_image_list))


def main():
    """Render the Jinja2 template file."""
    config_file_template_path = GIT_ROOT / ".circleci" / "config.yml.j2"
    config_file_path = GIT_ROOT / ".circleci" / "config.yml"

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
