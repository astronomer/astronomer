from tests.helm_template_generator import render_chart
import pytest
import yaml
from . import git_root_dir
from . import get_containers_by_name


with open(f"{git_root_dir}/tests/default_chart_data.yaml") as file:
    default_chart_data = yaml.load(file, Loader=yaml.SafeLoader)

template_ids = [template["name"] for template in default_chart_data]


@pytest.mark.parametrize("template", default_chart_data, ids=template_ids)
class TestAllCharts:
    pod_managers = ["Deployment", "StatefulSet", "DaemonSet"]

    def test_default_chart_with_basedomain(self, template):
        """Test that each template used with just baseDomain set renders."""
        docs = render_chart(
            show_only=[template["name"]],
        )
        assert len(docs) == template["length"]

        pod_manger_docs = [doc for doc in docs if doc["kind"] in self.pod_managers]
        for doc in pod_manger_docs:
            c_by_name = get_containers_by_name(doc, include_init_containers=True)
            for name, container in c_by_name.items():
                assert container[
                    "image"
                ], f"container {name} does not have an image: {doc}"
                assert container[
                    "imagePullPolicy"
                ], f"Template filename: {template['name']}\nContainer name '{name}' does not have an imagePullPolicy\ndoc: {doc}"

    def test_all_default_charts_with_private_registry(self, template):
        """Test that each chart uses the privateRegistry.

        This only finds default images, not the many which are hidden behind feature flags.
        """
        private_repo = "example.com/the-private-registry-repository"
        docs = render_chart(
            show_only=[template["name"]],
            values={
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        "repository": private_repo,
                    }
                }
            },
        )

        pod_manger_docs = [doc for doc in docs if doc["kind"] in self.pod_managers]
        for doc in pod_manger_docs:
            c_by_name = get_containers_by_name(doc)

            for name, container in c_by_name.items():
                assert container["image"].startswith(
                    private_repo
                ), f"The container '{name}' does not use the privateRegistry repo '{private_repo}': {container}"
