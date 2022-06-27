#!/usr/bin/env python3
import subprocess
from pathlib import Path

import docker

PUSH_IMAGE_REG = "mishah334.jfrog.io"
PUSH_IMAGE_REPO = "default-docker-local"
PUSH_IMAGE_USERNAME = "mishal.shah@astronomer.io"
PUSH_IMAGE_PASS = "AKCp8mZT1EnN98JMoiWs9uFZXNUd4akWuttojdgWjZ8ohQP1JNNtUGZFMLP7DgNPDWRLkjX5F"

docker_client = docker.from_env()


def list_docker_images(path):
    command = f"cd {path} && helm template . -f tests/enable_all_features.yaml 2>/dev/null | awk '/image: / {{print $2}}' | sed 's/\"//g' | sort -u"
    docker_images_output = subprocess.check_output(command, shell=True)
    docker_image_list = docker_images_output.decode("utf-8").strip().split("\n")

    return sorted(set(docker_image_list))


def pull_docker_image(docker_client, image):
    print("INFO: Pulling docker image: " + image)
    return docker_client.images.pull(image)


def push_docker_image(docker_client, image_client, pull_image_name):
    push_image_repo = pull_image_name.replace("quay.io/astronomer", PUSH_IMAGE_REG + "/" + PUSH_IMAGE_REPO)

    # Tagging
    tag_check = image_client.tag(
        repository=push_image_repo
    )

    if tag_check:
        print("INFO: Pushing docker image: " + push_image_repo)
        docker_client.images.push(
            repository=push_image_repo,
            auth_config={
                "username": PUSH_IMAGE_USERNAME,
                "password": PUSH_IMAGE_PASS
            }
        )
    else:
        print("ERROR: Tagging was not successful.")


def main():
    project_directory = Path(__file__).parent
    docker_images = list_docker_images(str(project_directory))

    for docker_image in docker_images:
        image_client = pull_docker_image(docker_client, docker_image)
        push_docker_image(docker_client, image_client, docker_image)


if __name__ == "__main__":
    main()
