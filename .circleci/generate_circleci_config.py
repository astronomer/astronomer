#!/usr/bin/env python3
"""
This script is used to create the circle config file
so that we can stay DRY.
"""
import os
import subprocess
from pathlib import Path

from jinja2 import Template

# When adding a new version, look up the most
# recent patch version on Dockerhub
# https://hub.docker.com/r/kindest/node/tags
# This should match what is in tests/__init__.py
KUBE_VERSIONS = ["1.19.11", "1.20.7", "1.21.2", "1.22.7", "1.23.4"]
CI_REMOTE_DOCKER_VERSION = "20.10.12"


def list_docker_images(path):
    command = "cd " + path + " && make show-docker-images-no-link"
    docker_images_output = subprocess.check_output(command, shell=True)
    docker_image_list = docker_images_output.decode("utf-8").strip().split("\n")

    return docker_image_list


def main():
    """Render the Jinja2 template file"""
    project_directory = Path(__file__).parent.parent
    circle_directory = os.path.dirname(os.path.realpath(__file__))
    config_template_path = os.path.join(circle_directory, "config.yml.j2")
    config_path = os.path.join(circle_directory, "config.yml")

    docker_images = list_docker_images(str(project_directory))

    with open(config_template_path) as circle_ci_config_template:
        templated_file_content = circle_ci_config_template.read()
    template = Template(templated_file_content)
    config = template.render(
        kube_versions=KUBE_VERSIONS,
        docker_images=docker_images,
        remote_docker_version=CI_REMOTE_DOCKER_VERSION,
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
