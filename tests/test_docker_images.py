import docker
from tests.helm_template_generator import render_chart
import jmespath


def test_docker_images(docker_client):

    extra_globals = {
        "global.baseDomain": "foo.com",
        "blackboxExporterEnabled": True,
        "postgresqlEnabled": True,
        "prometheusPostgresExporterEnabled": True,
        "pspEnabled": True,
        "veleroEnabled": True,
    }

    public_repo_docs = render_chart(values={"global": extra_globals})

    # Listing docker images
    search_string = "spec.template.spec.containers[*].image"
    docker_images = []
    for public_repo_doc in public_repo_docs:
        docker_image_sublist = jmespath.search(search_string, public_repo_doc)

        if docker_image_sublist is not None:
            docker_images = docker_image_sublist + docker_images

    # Pulling docker image test
    for docker_image in docker_images:
        if docker_image is not None:
            docker_image = docker_image.replace('"', "").strip()
            try:
                # Pulling docker image
                image = docker_client.images.pull(docker_image)
                print(docker_image + ": " + image.id)
            except docker.errors.APIError as exc:
                assert (
                    False
                ), f"'Unable to pull docker image: {docker_image} | Error: {exc}"
