import pytest

from tests import get_containers_by_name
from tests.chart_tests.helm_template_generator import render_chart
import re

annotation_validator = re.compile(
    "^([^/]+/)?(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])$"
)
pod_managers = ["Deployment", "StatefulSet", "DaemonSet"]


class TestAllPodSpecContainers:
    """Test pod spec containers for some defaults."""

    default_docs = render_chart()
    default_docs_trimmed = [doc for doc in default_docs if doc["kind"] in pod_managers]
    annotated = [x for x in default_docs if x["metadata"].get("annotations")]

    @pytest.mark.parametrize(
        "doc",
        annotated,
        ids=[f"{x['kind']}/{x['metadata']['name']}" for x in annotated],
    )
    def test_annotation_keys_are_valid(self, doc):
        """Test that our annotation keys are valid."""
        annotation_results = [
            bool(annotation_validator.match(a)) for a in doc["metadata"]["annotations"]
        ]
        assert all(
            annotation_results
        ), f"One of the annotation keys in {doc['kind']} {doc['metadata']['name']} is invalid."

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

        This only finds default images, not the many which are hidden
        behind feature flags.
        """
        c_by_name = get_containers_by_name(doc)

        for name, container in c_by_name.items():
            assert container["image"].startswith(
                self.private_repo
            ), f"The container '{name}' does not use the privateRegistry repo '{self.private_repo}': {container}"


@pytest.mark.skip(
    "See issue https://github.com/astronomer/issues/issues/5227 for details about when to reenabling this."
)
class TestDuplicateEnvironment:
    """Parametrize all the docs that have container specs and test them for
    duplicate env vars."""

    values = chart_tests.get_all_features()

    docs = render_chart(values=values)
    trimmed_docs = [x for x in docs if x["kind"] in pod_managers + ["CronJob"]]

    @staticmethod
    def check_env_vars_are_unique(container):
        """Return a list of env vars that are duplicates."""
        c_env_names = [x["name"] for x in container.get("env") or []]
        return [x for x in set(c_env_names) if c_env_names.count(x) > 1]

    @pytest.mark.parametrize(
        "doc",
        trimmed_docs,
        ids=[f"{x['kind']}/{x['metadata']['name']}" for x in trimmed_docs],
    )
    def test_env_vars_have_no_duplicates(self, doc):
        """Test that there are no duplicate env vars."""
        if doc["kind"] in pod_managers:
            for container in doc["spec"]["template"]["spec"].get("containers") or []:
                assert (
                    self.check_env_vars_are_unique(container) == []
                ), "container has duplicate env vars"

            for container in (
                doc["spec"]["template"]["spec"].get("initContainers") or []
            ):
                assert (
                    self.check_env_vars_are_unique(container) == []
                ), "initContainer has duplicate env vars"

        elif doc["kind"] == "CronJob":
            for container in (
                doc["spec"]["jobTemplate"]["spec"]["template"]["spec"].get("containers")
                or []
            ):
                assert (
                    self.check_env_vars_are_unique(container) == []
                ), "container has duplicate env vars"

            for container in (
                doc["spec"]["jobTemplate"]["spec"]["template"]["spec"].get(
                    "initContainers"
                )
                or []
            ):
                assert (
                    self.check_env_vars_are_unique(container) == []
                ), "initContainer has duplicate env vars"
