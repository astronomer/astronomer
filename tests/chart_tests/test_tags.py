from tests.chart_tests.helm_template_generator import render_chart
import pytest
import tests.chart_tests as chart_tests
import subprocess
from pathlib import Path


component_paths = [
    "charts/alertmanager/templates",
    "charts/grafana/templates",
    "charts/kube-state/templates",
    "charts/prometheus-blackbox-exporter/templates",
    "charts/prometheus-node-exporter/templates",
    "charts/prometheus-postgres-exporter/templates",
    "charts/prometheus/templates",
]

# Some charts have configs that are hard to test when parametrizing with get_all_features()
# eg: password vs passwordSecret
edge_cases = [
    "charts/prometheus-postgres-exporter/templates/secret.yaml",
]

show_only = [
    str(y)
    for x in component_paths
    for y in list(Path(x).glob("*.yaml"))
    if not y.name.startswith("_") and str(y) not in edge_cases
]

chart_values = chart_tests.get_all_features()


# We use kube_version=1.24 here because 1.25 removes psp, and we need to test psp. Once 1.24
# is deprecated we can set this to something higher, and will likely have to solve similar
# problems for newer api differences.
@pytest.mark.parametrize("template", show_only)
def test_tags_monitoring_enabled(
    template, chart_values=chart_values, kube_version="1.24.0"
):
    """Test that when monitoring is disabled, the monitoring components are not present."""
    chart_values["tags"] = {"monitoring": True}
    docs = render_chart(
        kube_version=kube_version, values=chart_values, show_only=template
    )

    assert len(docs) >= 1
    assert (
        template.split("/")[-1]
        .split("-")[-1]
        .removesuffix(".yaml")
        .replace("psp", "podsecuritypolicy")
        in docs[0]["kind"].lower()
    )


# We use kube_version=1.24 here because 1.25 removes psp, and we need to test psp. Once 1.24
# is deprecated we can set this to something higher, and will likely have to solve similar
# problems for newer api differences.
@pytest.mark.parametrize("template", show_only)
def test_tags_monitoring_disabled(
    template, chart_values=chart_values, kube_version="1.24.0"
):
    """Test that when monitoring is disabled, the monitoring components are not present."""
    chart_values["tags"] = {"monitoring": False}

    with pytest.raises(subprocess.CalledProcessError):
        render_chart(kube_version=kube_version, values=chart_values, show_only=template)
