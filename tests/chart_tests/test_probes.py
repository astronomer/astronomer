import pytest

import tests.chart_tests as chart_tests
from tests import supported_k8s_versions

include_kind_list = ["Deployment", "DaemonSet", "StatefulSet", "ReplicaSet"]
# TODO: these are the containers that lack readinessProbe and livenessProbe. We need to add probes if they
#       make sense and then remove them from the list. See https://github.com/astronomer/issues/issues/6606
#
# ignore_list is the get_chart_containers() key with the k8s version stripped off. For example:
# "1.30.0_release-name-houston-worker_houston" would be ignored with "release-name-houston-worker_houston"
ignore_list = [
    "release-name-alertmanager_alertmanager",
    "release-name-containerd-ca-update_cert-copy-and-toml-update",
    "release-name-elasticsearch-nginx_nginx",
    "release-name-external-es-proxy_awsproxy",
    "release-name-external-es-proxy_external-es-proxy",
    "release-name-fluentd_fluentd",
    "release-name-houston-worker_houston",
    "release-name-kibana_kibana",
    "release-name-kube-state_kube-state",
    "release-name-nats_metrics",
    "release-name-nginx-default-backend_default-backend",
    "release-name-private-ca_cert-copy",
    "release-name-stan_metrics",
]


def init_test_probes() -> dict:
    """Return a dict of all containers in the chart for the given kubernetes version.

    The keys for this dict are like <version>_<release-name>-<pod>_<container>
    EG: 1.30.0_release-name-houston-worker_houston
    """
    chart_values = chart_tests.get_all_features()

    return {
        k: v
        for k8s_version in supported_k8s_versions
        for k, v in chart_tests.get_chart_containers(k8s_version, chart_values, include_kinds=include_kind_list).items()
        if k not in [f"{k8s_version}_{i}" for i in ignore_list]
    }


chart_containers = init_test_probes()


@pytest.mark.parametrize("container", chart_containers.values(), ids=chart_containers.keys())
class TestProbes:
    def test_container_readiness_probes(self, container):
        """Ensure all containers have liveness and readiness probes."""

        if container["key"] in ignore_list:
            pytest.skip(f"Info: Unsupported resource: {container['key']}")
        elif not container.get("ports"):
            pytest.skip(f"Info: No ports found in container {container['key']} so readinessProbe is not applicable.")
        else:
            assert "readinessProbe" in container

    def test_container_liveness_probes(self, container):
        """Ensure all containers have liveness and readiness probes."""

        if container["key"] in ignore_list:
            pytest.skip(f"Info: Unsupported resource: {container['key']}")
        else:
            assert "livenessProbe" in container
