#!/usr/bin/env python3
"""This script is used to create the circle config file so that we can stay
DRY."""
import os
import subprocess
from pathlib import Path

from jinja2 import Template

# When adding a new version, look up the most
# recent patch version on Dockerhub
# This should match what is in tests/__init__.py
# https://hub.docker.com/r/kindest/node/tags
kube_versions = ["1.23.17", "1.24.15", "1.25.11", "1.26.6", "1.27.3"]
# https://circleci.com/docs/2.0/building-docker-images/#docker-version
ci_remote_docker_version = "20.10.24"
# https://circleci.com/developer/machine/image/ubuntu-2204
machine_image_version = "ubuntu-2204:2023.07.2"
ci_runner_version = "2023-09"


def list_docker_images(path):
    command = f"cd {path} && helm template . -f tests/enable_all_features.yaml 2>/dev/null | awk '/image: / {{print $2}}' | sed 's/\"//g' | sort -u"
    docker_images_output = subprocess.check_output(command, shell=True)
    docker_image_list = docker_images_output.decode("utf-8").strip().split("\n")

    return sorted(set(docker_image_list))


def main():
    """Render the Jinja2 template file."""
    project_directory = Path(__file__).parent.parent
    circle_directory = os.path.dirname(os.path.realpath(__file__))
    config_template_path = os.path.join(circle_directory, "config.yml.j2")
    config_path = os.path.join(circle_directory, "config.yml")

    docker_images = list_docker_images(str(project_directory))

    templated_file_content = Path(config_template_path).read_text()
    template = Template(templated_file_content)
    config = template.render(
        kube_versions=kube_versions,
        docker_images=docker_images,
        machine_image_version=machine_image_version,
        remote_docker_version=ci_remote_docker_version,
        ci_runner_version=ci_runner_version,
    )
    with open(config_path, "w") as circle_ci_config_file:
        warning_header = (
            "# Warning: automatically generated file\n"
            + "# Please edit config.yml.j2, and use the script generate_circleci_config.py\n"
        )
        circle_ci_config_file.write(warning_header)
        circle_ci_config_file.write(config)
        circle_ci_config_file.write("\n")


if __name__ == "__main__":
    main()
