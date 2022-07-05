import jmespath
import pytest

from tests.chart_tests.helm_template_generator import render_chart


def test_private_registry_repository_image_names_the_same_as_public_ones():
    """test that image names dont change when using a custom repo because that breaks
    pull-through caching proxies in use by various customers."""

    extra_globals = {
        "blackboxExporterEnabled": True,
        "postgresqlEnabled": True,
        "prometheusPostgresExporterEnabled": True,
        "pspEnabled": True,
        "veleroEnabled": True,
    }

    repository = "quay.io/astronomer"
    public_repo_docs = render_chart(values={"global": extra_globals})
    private_repo_docs = render_chart(
        values={
            "global": {
                "privateRegistry": {"enabled": True, "repository": repository},
                **extra_globals,
            }
        },
    )

    # should be same number of images regardless of where they come from
    assert len(public_repo_docs) == len(private_repo_docs)

    search_string = "spec.template.spec.containers[*].image"
    differently_named_images = []
    for public_repo_doc, private_repo_doc in zip(public_repo_docs, private_repo_docs):
        public_repo_images = jmespath.search(search_string, public_repo_doc)
        private_repo_images = jmespath.search(search_string, private_repo_doc)
        if public_repo_images is not None or private_repo_images is not None:
            assert len(public_repo_images) == len(private_repo_images)
            for public_repo_image, private_repo_image in zip(
                public_repo_images, private_repo_images
            ):
                if public_repo_image != private_repo_image:
                    print(
                        f"image name differs when using a private repo named same as public - {public_repo_image} vs {private_repo_image}"
                    )
                    differently_named_images.append(
                        (public_repo_image, private_repo_image)
                    )
    assert not differently_named_images, differently_named_images


def test_private_registry_repository_overrides_work():
    """image names should always contain the new repository when it is specified."""
    repository = "bob-the-registry"
    docs = render_chart(
        values={
            "global": {"privateRegistry": {"enabled": True, "repository": repository}}
        },
    )
    # there should be lots of image hits
    assert len(docs) > 50
    differently_named_images = []
    for doc in docs:
        doc_images = jmespath.search("spec.template.spec.containers[*].image", doc)
        if doc_images is not None:
            for image in doc_images:
                if not image.startswith(repository):
                    print(
                        f"{image} did not begin with specified repository - {repository}"
                    )
                    differently_named_images.append(image)
    assert not differently_named_images, differently_named_images


def get_private_registry_docs_image_pull_secrets():
    repository = "bob-the-registry"
    secret_name = "bob-the-registry-secret"

    kubernetes_objects = {
        "Deployment": "spec.template.spec.imagePullSecrets",
        "StatefulSet": "spec.template.spec.imagePullSecrets",
        "Job": "spec.template.spec.imagePullSecrets",
        "DaemonSet": "spec.template.spec.imagePullSecrets",
        "Pod": "spec.template.spec.imagePullSecrets",
        "CronJob": "spec.jobTemplate.spec.template.spec.imagePullSecrets",
    }

    docs = render_chart(
        values={
            "global": {
                "privateRegistry": {
                    "enabled": True,
                    "repository": repository,
                    "secretName": secret_name,
                }
            }
        },
    )

    searched_docs = []
    for key, val in kubernetes_objects.items():
        searched_doc = jmespath.search(
            "[?kind == `"
            + key
            + "`].{name: metadata.name, kind: kind, image_pull_secrets: "
            + val
            + "}",
            docs,
        )
        searched_docs = searched_docs + searched_doc

    formatted_docs = {}
    for searched_doc in searched_docs:
        name = searched_doc["name"] + "_" + searched_doc["kind"]
        formatted_docs[name] = searched_doc["image_pull_secrets"]

    return formatted_docs


private_registry_docs_image_pull_secrets = (
    get_private_registry_docs_image_pull_secrets()
)


@pytest.mark.parametrize(
    "image_pull_secrets",
    private_registry_docs_image_pull_secrets.values(),
    ids=private_registry_docs_image_pull_secrets.keys(),
)
def test_private_registry_repository_image_pull_secret(image_pull_secrets):
    """Specs must contain imagePullSecrets for private repository when it is specified."""
    assert image_pull_secrets is not None
    assert {"name": "bob-the-registry-secret"} in image_pull_secrets
