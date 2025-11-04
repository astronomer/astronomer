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
    "charts/prometheus/templates",
]

# Some charts have configs that are hard to test when parametrizing with get_all_features()
# eg: password vs passwordSecret
templates_to_exclude = [
    "charts/prometheus-postgres-exporter/templates",
    "charts/prometheus-postgres-exporter/templates/secret.yaml",
]

show_only = [
    str(y)
    for x in component_paths
    for y in list(Path(x).glob("*.yaml"))
    if not y.name.startswith("_") and str(y) not in templates_to_exclude
]

chart_values = chart_tests.get_all_features()


@pytest.mark.parametrize("template", show_only)
def test_tags_monitoring_enabled(template, chart_values=chart_values):
    """Test that when monitoring is disabled, the monitoring components are not present."""
    chart_values["tags"] = {"monitoring": True}
    docs = render_chart(values=chart_values, show_only=template)

    assert len(docs) >= 1


@pytest.mark.parametrize("template", show_only)
def test_tags_monitoring_disabled(template, chart_values=chart_values):
    """Test that when monitoring is disabled, the monitoring components are not present."""
    chart_values["tags"] = {"monitoring": False}

    with pytest.raises(subprocess.CalledProcessError):
        render_chart(values=chart_values, show_only=template)
