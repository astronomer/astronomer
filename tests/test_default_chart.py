from tests.helm_template_generator import render_chart
import pytest
from . import get_containers_by_name


pod_managers = ["Deployment", "StatefulSet", "DaemonSet"]


class TestAllPodSpecContainers:
    """Test pod spec containers for some defaults."""

    default_docs = render_chart()
    default_docs_trimmed = [doc for doc in default_docs if doc["kind"] in pod_managers]

    @pytest.mark.parametrize(
        "doc",
        default_docs_trimmed,
        ids=[f"{x['kind']}/{x['metadata']['name']}" for x in default_docs_trimmed],
    )
    def test_default_chart_with_basedomain(self, doc):
        """Test that each container in each pod spec renders."""
        c_by_name = get_containers_by_name(doc, include_init_containers=True)
        for name, container in c_by_name.items():
            assert container["image"], f"container {name} does not have an image: {doc}"
            assert container["imagePullPolicy"]

    private_repo = "example.com/the-private-registry-repository"
    private_repo_docs = render_chart(
        values={
            "global": {
                "privateRegistry": {
                    "enabled": True,
                    "repository": private_repo,
                }
            }
        },
    )
    private_repo_docs_trimmed = [
        doc for doc in private_repo_docs if doc["kind"] in pod_managers
    ]

    @pytest.mark.parametrize(
        "doc",
        private_repo_docs_trimmed,
        ids=[f"{x['kind']}/{x['metadata']['name']}" for x in private_repo_docs_trimmed],
    )
    def test_all_default_charts_with_private_registry(self, doc):
        """Test that each chart uses the privateRegistry.

        This only finds default images, not the many which are hidden behind feature flags.
        """
        c_by_name = get_containers_by_name(doc)

        for name, container in c_by_name.items():
            assert container["image"].startswith(
                self.private_repo
            ), f"The container '{name}' does not use the privateRegistry repo '{self.private_repo}': {container}"
