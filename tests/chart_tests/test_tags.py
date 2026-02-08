import subprocess
from pathlib import Path

import pytest

from tests import newest_supported_kube_version
from tests.utils import get_all_features
from tests.utils.chart import render_chart

component_paths = [
    "charts/alertmanager/templates",
    "charts/grafana/templates",
    "charts/kube-state/templates",
    "charts/prometheus/templates",
]

# Some charts have configs that are hard to test when parametrizing with get_all_features()
# eg: password vs passwordSecret
templates_to_exclude = [
    "charts/prometheus-postgres-exporter/templates",
    "charts/prometheus-postgres-exporter/templates/secret.yaml",
    "charts/alertmanager/templates/alertmanager-serviceaccount.yaml",
    "charts/prometheus/templates/prometheus-federate-networkpolicy.yaml",
]

show_only = [
    str(y)
    for x in component_paths
    for y in list(Path(x).glob("*.yaml"))
    if not y.name.startswith("_") and str(y) not in templates_to_exclude
]

chart_values = get_all_features()


@pytest.mark.parametrize("template", show_only)
def test_tags_monitoring_enabled(template, chart_values=chart_values, kube_version=newest_supported_kube_version):
    """Test that when monitoring is enabled, the monitoring components are not present."""
    chart_values["tags"] = {"monitoring": True}
    if "auth-sidecar" in template:
        chart_values["global"] = {"plane": {"mode": "control"}, "authSidecar": {"enabled": True}}
    elif "prometheus-federate-ingress" in template or "prometheus-federation-auth" in template:
        chart_values["global"] = {"plane": {"mode": "data"}}
    else:
        chart_values["global"] = {"plane": {"mode": "unified"}}
    docs = render_chart(kube_version=kube_version, values=chart_values, show_only=template)
    assert len(docs) >= 1


@pytest.mark.parametrize("template", show_only)
def test_tags_monitoring_disabled(template, chart_values=chart_values, kube_version=newest_supported_kube_version):
    """Test that when monitoring is disabled, no monitoring components are present."""
    chart_values["tags"] = {"monitoring": False}

    with pytest.raises(subprocess.CalledProcessError):
        render_chart(kube_version=kube_version, values=chart_values, show_only=template)
