import jmespath
import pytest

import tests.chart_tests as chart_tests
from tests.chart_tests.helm_template_generator import render_chart


def init_test_svc_port_configs():
    chart_values = chart_tests.get_all_features()

    docs = render_chart(values=chart_values)

    svc_docs = jmespath.search(
        "[?kind == 'Service'].{name: metadata.name, chart: metadata.labels.chart, component: metadata.labels.component, ports: spec.ports}",
        docs,
    )

    return {
        f'{doc["chart"]}_{doc["component"]}_{doc["name"]}': doc["ports"]
        for doc in svc_docs
    }


test_svc_port_configs_data = init_test_svc_port_configs()


@pytest.mark.parametrize(
    "svc_ports",
    test_svc_port_configs_data.values(),
    ids=test_svc_port_configs_data.keys(),
)
def test_svc_port_configs(svc_ports):
    """Port specs must contain appProtocol in Svc definition."""
    assert svc_ports is not None

    for svc_port in svc_ports:

        if svc_port['name'] == 'default-backend':
            pytest.skip("Skipping test for Nginx default backend.")

        assert "appProtocol" in svc_port
        assert "name" in svc_port
        assert "port" in svc_port
