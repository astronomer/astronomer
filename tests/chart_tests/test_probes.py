import pytest

import tests.chart_tests as chart_tests
from tests import supported_k8s_versions

ignore_kind_list = []
ignore_list = [
    "1.19.0_release-name-elasticsearch-nginx_nginx",
    "1.19.0_release-name-external-es-proxy_external-es-proxy",
    "1.19.0_release-name-external-es-proxy_awsproxy",
    "1.19.0_release-name-kibana_kibana",
    "1.19.0_release-name-kube-state_kube-state",
    "1.19.0_release-name-nginx-default-backend_default-backend",
    "1.19.0_release-name-nginx_nginx",
    "1.19.0_release-name-elasticsearch-data_es-data",
    "1.19.0_release-name-nats_metrics",
    "1.19.0_release-name-prometheus_configmap-reloader",
    "1.19.0_release-name-stan_metrics",
    "1.19.0_release-name-houston-db-migrations_houston-db-migrations-job",
    "1.19.0_release-name-houston-upgrade-deployments_post-upgrade-job",
    "1.20.0_release-name-fluentd_fluentd",
    "1.20.0_release-name-cli-install_cli-install",
    "1.20.0_release-name-houston-worker_houston",
    "1.20.0_release-name-elasticsearch-nginx_nginx",
    "1.20.0_release-name-external-es-proxy_external-es-proxy",
    "1.20.0_release-name-external-es-proxy_awsproxy",
    "1.20.0_release-name-kibana_kibana",
    "1.20.0_release-name-kube-state_kube-state",
    "1.20.0_release-name-nginx-default-backend_default-backend",
    "1.20.0_release-name-nginx_nginx",
    "1.20.0_release-name-elasticsearch-data_es-data",
    "1.20.0_release-name-nats_metrics",
    "1.20.0_release-name-prometheus_configmap-reloader",
    "1.20.0_release-name-stan_metrics",
    "1.20.0_release-name-houston-db-migrations_houston-db-migrations-job",
    "1.20.0_release-name-houston-upgrade-deployments_post-upgrade-job",
    "1.21.0_release-name-fluentd_fluentd",
    "1.21.0_release-name-cli-install_cli-install",
    "1.21.0_release-name-houston-worker_houston",
    "1.21.0_release-name-elasticsearch-nginx_nginx",
    "1.21.0_release-name-external-es-proxy_external-es-proxy",
    "1.21.0_release-name-external-es-proxy_awsproxy",
    "1.21.0_release-name-kibana_kibana",
    "1.21.0_release-name-kube-state_kube-state",
    "1.21.0_release-name-nginx-default-backend_default-backend",
    "1.21.0_release-name-nginx_nginx",
    "1.21.0_release-name-elasticsearch-data_es-data",
    "1.21.0_release-name-nats_metrics",
    "1.21.0_release-name-prometheus_configmap-reloader",
    "1.21.0_release-name-stan_metrics",
    "1.21.0_release-name-houston-db-migrations_houston-db-migrations-job",
    "1.21.0_release-name-houston-upgrade-deployments_post-upgrade-job",
    "1.22.0_release-name-fluentd_fluentd",
    "1.22.0_release-name-cli-install_cli-install",
    "1.22.0_release-name-houston-worker_houston",
    "1.22.0_release-name-elasticsearch-nginx_nginx",
    "1.22.0_release-name-external-es-proxy_external-es-proxy",
    "1.22.0_release-name-external-es-proxy_awsproxy",
    "1.22.0_release-name-kibana_kibana",
    "1.22.0_release-name-kube-state_kube-state",
    "1.22.0_release-name-nginx-default-backend_default-backend",
    "1.22.0_release-name-nginx_nginx",
    "1.22.0_release-name-elasticsearch-data_es-data",
    "1.22.0_release-name-nats_metrics",
    "1.22.0_release-name-prometheus_configmap-reloader",
    "1.22.0_release-name-stan_metrics",
    "1.22.0_release-name-houston-db-migrations_houston-db-migrations-job",
    "1.22.0_release-name-houston-upgrade-deployments_post-upgrade-job",
    "1.23.0_release-name-fluentd_fluentd",
    "1.23.0_release-name-cli-install_cli-install",
    "1.23.0_release-name-houston-worker_houston",
    "1.23.0_release-name-elasticsearch-nginx_nginx",
    "1.23.0_release-name-external-es-proxy_external-es-proxy",
    "1.23.0_release-name-external-es-proxy_awsproxy",
    "1.23.0_release-name-kibana_kibana",
    "1.23.0_release-name-kube-state_kube-state",
    "1.23.0_release-name-nginx-default-backend_default-backend",
    "1.23.0_release-name-nginx_nginx",
    "1.23.0_release-name-elasticsearch-data_es-data",
    "1.23.0_release-name-nats_metrics",
    "1.23.0_release-name-prometheus_configmap-reloader",
    "1.23.0_release-name-stan_metrics",
    "1.23.0_release-name-houston-db-migrations_houston-db-migrations-job",
    "1.23.0_release-name-houston-upgrade-deployments_post-upgrade-job",
    "1.19.0_release-name-houston-worker_houston",
    "1.19.0_release-name-elasticsearch-nginx_nginx",
    "1.19.0_release-name-external-es-proxy_external-es-proxy",
    "1.19.0_release-name-external-es-proxy_awsproxy",
    "1.19.0_release-name-kibana_kibana",
    "1.19.0_release-name-alertmanager_alertmanager",
    "1.19.0_release-name-nats_metrics",
    "1.19.0_release-name-prometheus_configmap-reloader",
    "1.19.0_release-name-stan_metrics",
    "1.19.0_release-name-houston-db-migrations_houston-db-migrations-job",
    "1.19.0_release-name-houston-upgrade-deployments_post-upgrade-job",
    "1.19.0_release-name-fluentd_fluentd",
    "1.19.0_release-name-cli-install_cli-install",
    "1.19.0_release-name-houston-worker_houston",
    "1.20.0_release-name-houston-worker_houston",
    "1.20.0_release-name-elasticsearch-nginx_nginx",
    "1.20.0_release-name-external-es-proxy_external-es-proxy",
    "1.20.0_release-name-external-es-proxy_awsproxy",
    "1.20.0_release-name-kibana_kibana",
    "1.20.0_release-name-alertmanager_alertmanager",
    "1.20.0_release-name-nats_metrics",
    "1.20.0_release-name-prometheus_configmap-reloader",
    "1.20.0_release-name-stan_metrics",
    "1.20.0_release-name-houston-db-migrations_houston-db-migrations-job",
    "1.20.0_release-name-houston-upgrade-deployments_post-upgrade-job",
    "1.21.0_release-name-houston-worker_houston",
    "1.21.0_release-name-elasticsearch-nginx_nginx",
    "1.21.0_release-name-external-es-proxy_external-es-proxy",
    "1.21.0_release-name-external-es-proxy_awsproxy",
    "1.21.0_release-name-kibana_kibana",
    "1.21.0_release-name-alertmanager_alertmanager",
    "1.21.0_release-name-nats_metrics",
    "1.21.0_release-name-prometheus_configmap-reloader",
    "1.21.0_release-name-stan_metrics",
    "1.21.0_release-name-houston-db-migrations_houston-db-migrations-job",
    "1.21.0_release-name-houston-upgrade-deployments_post-upgrade-job",
    "1.22.0_release-name-houston-worker_houston",
    "1.22.0_release-name-elasticsearch-nginx_nginx",
    "1.22.0_release-name-external-es-proxy_external-es-proxy",
    "1.22.0_release-name-external-es-proxy_awsproxy",
    "1.22.0_release-name-kibana_kibana",
    "1.22.0_release-name-alertmanager_alertmanager",
    "1.22.0_release-name-nats_metrics",
    "1.22.0_release-name-prometheus_configmap-reloader",
    "1.22.0_release-name-stan_metrics",
    "1.22.0_release-name-houston-db-migrations_houston-db-migrations-job",
    "1.22.0_release-name-houston-upgrade-deployments_post-upgrade-job",
    "1.23.0_release-name-houston-worker_houston",
    "1.23.0_release-name-elasticsearch-nginx_nginx",
    "1.23.0_release-name-external-es-proxy_external-es-proxy",
    "1.23.0_release-name-external-es-proxy_awsproxy",
    "1.23.0_release-name-kibana_kibana",
    "1.23.0_release-name-alertmanager_alertmanager",
    "1.23.0_release-name-nats_metrics",
    "1.23.0_release-name-prometheus_configmap-reloader",
    "1.23.0_release-name-stan_metrics",
    "1.23.0_release-name-houston-db-migrations_houston-db-migrations-job",
    "1.23.0_release-name-houston-upgrade-deployments_post-upgrade-job",
]


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
