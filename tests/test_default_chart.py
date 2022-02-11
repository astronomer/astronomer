from tests.helm_template_generator import render_chart
import pytest
import yaml
from . import git_root_dir

# TODO: find a way to easily update this default_chart_data.yaml EG when new files are added
# TODO: add more checks that should apply to all manifests of a given type like how we check that all pod_managers have imagePullPolicy
with open(f"{git_root_dir}/tests/default_chart_data.yaml") as file:
    default_chart_data = yaml.load(file, Loader=yaml.SafeLoader)

template_ids = [template["name"] for template in default_chart_data]


@pytest.mark.parametrize("template", default_chart_data, ids=template_ids)
def test_default_chart_with_basedomain(template):
    """Test that each template used with just baseDomain set renders and all standard properties are present."""
    docs = render_chart(
        show_only=[template["name"]],
    )
    assert len(docs) == template["length"]

    pod_managers = ["Deployment", "StatefulSet", "DaemonSet"]

    pod_manger_docs = [doc for doc in docs if doc["kind"] in pod_managers]

    for doc in pod_manger_docs:
        c_by_name = {
            c["name"]: c for c in doc["spec"]["template"]["spec"].get("containers")
        }

        if doc["spec"]["template"]["spec"].get("initContainers"):
            c_by_name.update(
                {
                    c["name"]: c
                    for c in doc["spec"]["template"]["spec"].get("containers")
                }
            )

        for name, container in c_by_name.items():
            assert container[
                "imagePullPolicy"
            ], f"container {name} does not have an imagePullPolicy: {doc}"

        # breakpoint()
