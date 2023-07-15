from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
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

show_only = [
    str(y)
    for x in component_paths
    for y in list(Path(x).glob("*.yaml"))
    if not y.name.startswith("_")
]

chart_values = chart_tests.get_all_features()


@pytest.mark.parametrize("template", show_only)
@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_tags_monitoring_enabled(kube_version, template, chart_values=chart_values):
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


@pytest.mark.parametrize("template", show_only)
@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_tags_monitoring_disabled(kube_version, template, chart_values=chart_values):
    """Test that when monitoring is disabled, the monitoring components are not present."""
    chart_values["tags"] = {"monitoring": False}

    with pytest.raises(subprocess.CalledProcessError):
        render_chart(kube_version=kube_version, values=chart_values, show_only=template)
