from tests.helm_template_generator import render_chart
import jmespath


def test_private_repository_image_names_the_same_as_public_ones():
    """test that image names dont change when using a custom repo because that breaks
    pull-through caching proxies in use by various customers"""
    repository = "quay.io/astronomer"
    public_repo_docs = render_chart()
    private_repo_docs = render_chart(
        values={
            "global": {"privateRegistry": {"enabled": True, "repository": repository}}
        },
    )
    # should be same number of images regardless of where they come from
    assert len(public_repo_docs) == len(private_repo_docs)
    search_string = "spec.template.spec.containers[*].image"
    differtly_named_images = []
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
                    differtly_named_images.append(
                        (private_repo_image, public_repo_image)
                    )
    assert len(differtly_named_images) == 0


def test_repository_overrides_work():
    """image names should always contain the new repository is specified"""
    repository = "bob-the-registry"
    docs = render_chart(
        values={
            "global": {"privateRegistry": {"enabled": True, "repository": repository}}
        },
    )
    # there should be lots of image hits
    assert len(docs) > 50
    differtly_named_images = []
    for doc in docs:
        documentImages = jmespath.search("spec.template.spec.containers[*].image", doc)
        if documentImages is not None:
            for image in documentImages:
                if not image.startswith(repository):
                    print(
                        f"{image} did not begin with specified repository - {repository}"
                    )
                    differtly_named_images.append(image)
    assert len(differtly_named_images) == 0
