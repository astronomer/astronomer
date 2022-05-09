import pytest

import tests.chart_tests as chart_tests
from tests import supported_k8s_versions

ignore_kind_list = ["Deployment", "StatefulSet", "Job", "DaemonSet"]
ignore_list = []


def init_test_probes():
    chart_values = chart_tests.get_all_features()

    containers = {}
    for k8s_version in supported_k8s_versions:
        k8s_version_containers = chart_tests.get_chart_containers(
            k8s_version, chart_values, ignore_kind_list
        )
        containers = {**containers, **k8s_version_containers}

    return containers


class TestProbes:
    chart_containers = init_test_probes()

    @pytest.mark.parametrize(
        "container", chart_containers.values(), ids=chart_containers.keys()
    )
    def test_container_readiness_probes(self, container):
        """Ensure all containers have liveness and readiness probes"""

        if container["key"] in ignore_list:
            pytest.skip("Info: Unsupported resource: " + container["key"])
        else:
            assert "readinessProbe" in container

    @pytest.mark.parametrize(
        "container", chart_containers.values(), ids=chart_containers.keys()
    )
    def test_container_liveness_probes(self, container):
        """Ensure all containers have liveness and readiness probes"""

        if container["key"] in ignore_list:
            pytest.skip("Info: Unsupported resource: " + container["key"])
        else:
            assert "livenessProbe" in container
