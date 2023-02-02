import pytest

import tests.chart_tests as chart_tests
from tests import supported_k8s_versions
import re

ignore_kind_list = ["Job"]
ignore_list = [
    "fluentd_fluentd",
    "elasticsearch-exporter_metrics-exporter",
    "elasticsearch-nginx_nginx",
]


def init_test_non_root_user(kube_version: str) -> dict:
    """Return a dict of container specs for the given k8s version"""
    chart_values = chart_tests.get_all_features()
    containers = {}
    kube_version_containers = chart_tests.get_chart_containers(
        kube_version, chart_values, ignore_kind_list
    )
    return {**containers, **kube_version_containers}


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestProbes:
    def test_container_runasnonroot(self, kube_version):
        """Ensure all containers have runAsNonRoot."""

        containers = init_test_non_root_user(kube_version)

        for container in containers.values():
            if re.split("(?<=name-)(.*$)", container["key"])[1] in ignore_list:
                pytest.skip("Info: Resource needs root access" + container["key"])
            else:
                assert container.get("securityContext").get("runAsNonRoot") is True
