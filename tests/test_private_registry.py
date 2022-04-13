from tests.helm_template_generator import render_chart
import jmespath


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
