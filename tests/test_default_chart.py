from tests.helm_template_generator import render_chart
import pytest
import yaml
from . import git_root_dir


with open(f"{git_root_dir}/tests/default_chart_data.yaml") as file:
    default_chart_data = yaml.load(file, Loader=yaml.SafeLoader)

template_ids = [template["name"] for template in default_chart_data]


@pytest.mark.parametrize("template", default_chart_data, ids=template_ids)
def test_default_chart_with_basedomain(template):
    """Test that each template used with just baseDomain set renders."""
    docs = render_chart(
        show_only=[template["name"]],
    )
    assert len(docs) == template["length"]
