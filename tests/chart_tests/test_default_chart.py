import re

import pytest

import tests.chart_tests as chart_tests
from tests import get_containers_by_name
from tests.chart_tests.helm_template_generator import render_chart

annotation_validator = re.compile(
    "^([^/]+/)?(([A-Za-z0-9][-A-Za-z0-9_.]*)?[A-Za-z0-9])$"
)
pod_managers = ["Deployment", "StatefulSet", "DaemonSet"]


class TestAllCronJobs:
    chart_values = chart_tests.get_all_features()

    def test_ensure_cronjob_names_are_max_52_chars(self):
        """Cronjob names must be DNS_MAX_LEN - TIMESTAMP_LEN, which is 52 chars."""
        default_docs = render_chart(values=self.chart_values)
        cronjobs = [
            doc for doc in default_docs if doc["kind"].lower() == "CronJob".lower()
        ]

        for doc in cronjobs:
            name_len = len(doc["metadata"]["name"])
            assert (
                name_len <= 52
            ), f'{doc["metadata"]["name"]} is too long at {name_len} characters'


class TestAllPodSpecContainers:
    """Test pod spec containers for some defaults."""

    chart_values = chart_tests.get_all_features()

    default_docs = render_chart(values=chart_values)
    pod_manager_docs = [doc for doc in default_docs if doc["kind"] in pod_managers]
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
        pod_manager_docs,
        ids=[f"{x['kind']}/{x['metadata']['name']}" for x in pod_manager_docs],
    )
    def test_default_chart_with_basedomain(self, doc):
        """Test that each container in each pod spec renders and has some
        required fields."""
        c_by_name = get_containers_by_name(doc, include_init_containers=True)
        for name, container in c_by_name.items():
            assert container["image"], f"container {name} does not have an image: {doc}"
            assert container["imagePullPolicy"] == "IfNotPresent"

            resources = c_by_name[name]["resources"]
            assert "cpu" in resources.get("limits")
            assert "memory" in resources.get("limits")
            assert "cpu" in resources.get("requests")
            assert "memory" in resources.get("requests")

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
