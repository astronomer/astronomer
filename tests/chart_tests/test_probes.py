import pytest

import tests.chart_tests as chart_tests
from tests import supported_k8s_versions

ignore_kind_list = []
ignore_list = []


def init_test_probes() -> dict:
    """Return a dict of all containers in the chart for the given kubernetes version.

    The keys for this dict are like <version>_<release-name>-<pod>_<container>
    EG: 1.30.0_release-name-houston-worker_houston
    """
    chart_values = chart_tests.get_all_features()

    return {
        k: v
        for k8s_version in supported_k8s_versions
        for k, v in chart_tests.get_chart_containers(k8s_version, chart_values, ignore_kind_list).items()
    }


chart_containers = init_test_probes()


@pytest.mark.parametrize("container", chart_containers.values(), ids=chart_containers.keys())
class TestProbes:
    def test_container_readiness_probes(self, container):
        """Ensure all containers have liveness and readiness probes."""

        if container["key"] in ignore_list:
            pytest.skip("Info: Unsupported resource: " + container["key"])
        else:
            assert "readinessProbe" in container

    def test_container_liveness_probes(self, container):
        """Ensure all containers have liveness and readiness probes."""

        if container["key"] in ignore_list:
            pytest.skip("Info: Unsupported resource: " + container["key"])
        else:
            assert "livenessProbe" in container
