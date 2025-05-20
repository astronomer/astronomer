import pytest

from tests import supported_k8s_versions
from tests.utils import get_all_features, get_chart_containers

ignore_list = [
    "fluentd_fluentd",
    "elasticsearch-exporter_metrics-exporter",
    "elasticsearch-nginx_nginx",
]


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_container_runasnonroot(kube_version):
    """Ensure all containers have runAsNonRoot."""

    containers = get_chart_containers(kube_version, get_all_features())

    for container in containers.values():
        if container["key"].split("release-name-")[-1] in ignore_list:
            pytest.skip("Info: Resource needs root access" + container["key"])
        else:
            assert container.get("securityContext").get("runAsNonRoot") is True
