import pytest

import tests.chart_tests as chart_tests
from tests import supported_k8s_versions

ignore_kind_list = ["Job"]
ignore_list = [
    "fluentd_fluentd",
    "elasticsearch-exporter_metrics-exporter",
    "elasticsearch-nginx_nginx",
]


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestProbes:
    def test_container_runasnonroot(self, kube_version):
        """Ensure all containers have runAsNonRoot."""

        containers = chart_tests.get_chart_containers(
            kube_version, chart_tests.get_all_features(), ignore_kind_list
        )

        for container in containers.values():
            if container["key"].split("release-name-")[-1] in ignore_list:
                pytest.skip("Info: Resource needs root access" + container["key"])
            else:
                assert container.get("securityContext").get("runAsNonRoot") is True
