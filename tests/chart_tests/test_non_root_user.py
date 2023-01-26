import pytest

import tests.chart_tests as chart_tests
from tests import supported_k8s_versions

ignore_kind_list = ["Job"]
ignore_list = []


def init_test_non_root_user():
    chart_values = chart_tests.get_all_features()

    containers = {}
    for k8s_version in supported_k8s_versions:
        k8s_version_containers = chart_tests.get_chart_containers(
            k8s_version, chart_values, ignore_kind_list
        )
        containers = {**containers, **k8s_version_containers}

    return containers


class TestProbes:
    chart_containers = init_test_non_root_user()

    @pytest.mark.parametrize(
        "container", chart_containers.values(), ids=chart_containers.keys()
    )
    def test_container_runasnonroot(self, container):
        """Ensure all containers have liveness and readiness probes."""

        if container["key"] in ignore_list:
            pytest.skip("Info: Unsupported resource: " + container["key"])
        else:
            assert container.get("securityContext").get("runAsNonRoot") is True
