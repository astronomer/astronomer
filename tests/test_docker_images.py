import subprocess
import docker


def test_docker_images(docker_client):
    # Listing docker images
    list_docker_images_command = ["make", "list-docker-images"]
    docker_images = (
        subprocess.check_output(list_docker_images_command).decode().strip().split("\n")
    )

    for docker_image in docker_images:
        docker_image = docker_image.replace('"', "").strip()
        try:
            # Pulling docker image
            image = docker_client.images.pull(docker_image)
            print(docker_image + ": " + image.id)
        except docker.errors.APIError as exc:
            assert False, f"'Unable to pull docker image: {docker_image} | Error: {exc}"
