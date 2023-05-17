from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import yaml
import jmespath


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusConfigConfigmap:
    show_only = [
        "charts/prometheus/templates/prometheus-config-configmap.yaml"]

    def test_prometheus_config_configmap(self, kube_version):
        """Validate the prometheus config configmap and its embedded data."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
        )

        assert len(docs) == 1

        doc = docs[0]

        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-prometheus-config"

        config_yaml = yaml.safe_load(doc["data"]["config"])
        assert [
            x["tls_config"]["insecure_skip_verify"]
            for x in list(config_yaml["scrape_configs"])
            if x["job_name"] == "kubernetes-apiservers"
        ] == [False]

    def test_prometheus_config_configmap_with_different_name_and_ns(self, kube_version):
        """Validate the prometheus config configmap does not conflate
        deployment name and namespace."""
        doc = render_chart(
            name="foo-name",
            namespace="bar-ns",
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "blackboxExporterEnabled": True,
                    "veleroEnabled": True,
                    "prometheusPostgresExporterEnabled": True,
                    "nodeExporterEnabled": True,
                },
                "tcpProbe": {"enabled": True},
            },
        )[0]

        config_yaml = yaml.safe_load(doc["data"]["config"])
        targets = [
            x["static_configs"][0]["targets"]
            for x in config_yaml["scrape_configs"]
            if x["job_name"] == "blackbox HTTP"
        ][0]

        target_checks = [
            "http://foo-name-cli-install.bar-ns",
            "http://foo-name-commander.bar-ns:8880/healthz",
            "http://foo-name-elasticsearch.bar-ns:9200/_cluster/health?local=true",
            "http://foo-name-grafana.bar-ns:3000/api/health",
            "http://foo-name-houston.bar-ns:8871/v1/healthz",
            "http://foo-name-kibana.bar-ns:5601",
            "http://foo-name-registry.bar-ns:5000",
            "https://app.example.com",
            "https://houston.example.com/v1/healthz",
            "https://install.example.com",
            "https://registry.example.com",
        ]
        assert all(x in targets for x in target_checks)

    def test_prometheus_config_configmap_external_labels(self, kube_version):
        """Prometheus should have an external_labels section in config.yaml
        when external_labels is specified in helm values."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "prometheus": {
                    "external_labels": {
                        "external_labels_key_1": "external_labels_value_1"
                    }
                }
            },
        )[0]

        config_yaml = yaml.safe_load(doc["data"]["config"])
        assert config_yaml["global"]["external_labels"] == {
            "external_labels_key_1": "external_labels_value_1"
        }

    def test_promethesu_config_configmap_remote_write(self, kube_version):
        """Prometheus should have a remote_write section in config.yaml when
        remote_write is specified in helm values."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "prometheus": {
                    "remote_write": [
                        {
                            "url": "http://remote/write/url/",
                            "bearer_token": "remote_write_bearer_token",
                            "write_relabel_configs": [
                                {
                                    "source_labels": ["__name__"],
                                    "regex": "some_regex",
                                    "action": "keep",
                                }
                            ],
                        }
                    ]
                }
            },
        )[0]

        config_yaml = yaml.safe_load(doc["data"]["config"])
        assert config_yaml["remote_write"] == [
            {
                "bearer_token": "remote_write_bearer_token",
                "url": "http://remote/write/url/",
                "write_relabel_configs": [
                    {
                        "action": "keep",
                        "regex": "some_regex",
                        "source_labels": ["__name__"],
                    }
                ],
            }
        ]

    def test_prometheus_config_configmap_with_node_exporter(self, kube_version):
        """Validate the prometheus config configmap has the node-exporter
        enabled with params."""
        doc = render_chart(
            name="foo-name",
            namespace="bar-ns",
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "nodeExporterEnabled": True,
                },
            },
        )[0]

        nodeExporterConfigs = [
            x
            for x in yaml.safe_load(doc["data"]["config"])["scrape_configs"]
            if x["job_name"] == "node-exporter"
        ]
        assert nodeExporterConfigs[0]["job_name"] == "node-exporter"

    def test_prometheus_config_configmap_without_node_exporter(self, kube_version):
        """Validate the prometheus config configmap does not have node-exporter
        when it is not enabled."""
        doc = render_chart(
            name="foo-name",
            namespace="bar-ns",
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "nodeExporterEnabled": False,
                },
            },
        )[0]

        config_yaml = yaml.safe_load(doc["data"]["config"])
        job_names = [x["job_name"] for x in config_yaml["scrape_configs"]]
        assert "node-exporter" not in job_names

    def test_prometheus_config_release_relabel(self, kube_version):
        """Prometheus should have a regex for release name."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={"global": {"features": {"namespacePools": {"enabled": False}}},
                    "astronomer": {
                    "houston": {
                        "config": {"deployments": {"namespaceFreeFormEntry": False}},
                    },
            },
            },
        )[0]

        config = yaml.safe_load(doc["data"]["config"])
        scrape_config_search_result = jmespath.search(
            "scrape_configs[?job_name == 'kube-state']", config
        )
        metric_relabel_config_search_result = jmespath.search(
            "metric_relabel_configs[?target_label == 'release']",
            scrape_config_search_result[0],
        )
        print("metric_relabel_config_search_result..",
              metric_relabel_config_search_result)

        assert len(metric_relabel_config_search_result) == 1
        assert metric_relabel_config_search_result[0]["source_labels"] == [
            'namespace']
        assert metric_relabel_config_search_result[0][
            "regex"] == "^{{ .Release.Namespace }}-(.*$)"
        assert metric_relabel_config_search_result[0]["replacement"] == "$1"
        assert metric_relabel_config_search_result[0]["target_label"] == 'release'

    def test_prometheus_config_release_relabel_with_free_from_namespace(
        self, kube_version
    ):
        """Prometheus should not have a regex for release name when free form
        namespace is enabled."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {"namespaceFreeFormEntry": True},
            },
        )[0]

        config = yaml.safe_load(doc["data"]["config"])
        scrape_config_search_result = jmespath.search(
            "scrape_configs[?job_name == 'kube-state']", config
        )
        metric_relabel_config_search_result = jmespath.search(
            "metric_relabel_configs[?target_label == 'release']",
            scrape_config_search_result[0],
        )

        assert len(metric_relabel_config_search_result) == 2
        assert metric_relabel_config_search_result[0][
            "regex"] == '(.*?)(?:-webserver.*|-scheduler.*|-cleanup.*|-pgbouncer.*|-statsd.*|-triggerer.*|-run-airflow-migrations.*)?$'
        assert metric_relabel_config_search_result[0]["source_labels"] == [
            'pod']
        assert metric_relabel_config_search_result[0]["replacement"] == '$1'
        assert metric_relabel_config_search_result[0]["target_label"] == 'release'

        assert metric_relabel_config_search_result[1]["regex"] == '(.+)-resource-quota$'
        assert metric_relabel_config_search_result[1]["source_labels"] == [
            'resourcequota']
        assert metric_relabel_config_search_result[1]["replacement"] == '$1'
        assert metric_relabel_config_search_result[1]["target_label"] == 'release'

    def test_prometheus_config_insecure_skip_verify(self, kube_version):
        """Test that insecure_skip_verify is rendered correctly in the config when specified."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "prometheus": {
                    "config": {
                        "scrape_configs": {
                            "kubernetes_apiservers": {
                                "tls_config": {"insecure_skip_verify": True}
                            }
                        }
                    },
                },
            },
        )[0]

        config_yaml = yaml.safe_load(doc["data"]["config"])
        assert [
            x["tls_config"]["insecure_skip_verify"]
            for x in list(config_yaml["scrape_configs"])
            if x["job_name"] == "kubernetes-apiservers"
        ] == [True]
        
    def test_prometheus_config_release_relabel_with_pre_created_namespace(
        self, kube_version
    ):
        """Prometheus should have a regex for release name when namespacePools
        namespace is enabled."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {"features": {"namespacePools": {"enabled": True}}, "namespaceFreeFormEntry": False}
            },
        )[0]

        config = yaml.safe_load(doc["data"]["config"])
        scrape_config_search_result = jmespath.search(
            "scrape_configs[?job_name == 'kube-state']", config
        )
        metric_relabel_config_search_result = jmespath.search(
            "metric_relabel_configs[?target_label == 'release']",
            scrape_config_search_result[0],
        )

        assert len(metric_relabel_config_search_result) == 2
        assert metric_relabel_config_search_result[0][
            "regex"] == '(.*?)(?:-webserver.*|-scheduler.*|-cleanup.*|-pgbouncer.*|-statsd.*|-triggerer.*|-run-airflow-migrations.*)?$'
        assert metric_relabel_config_search_result[0]["source_labels"] == [
            'pod']
        assert metric_relabel_config_search_result[0]["replacement"] == '$1'
        assert metric_relabel_config_search_result[0]["target_label"] == 'release'

        assert metric_relabel_config_search_result[1]["regex"] == '(.+)-resource-quota$'
        assert metric_relabel_config_search_result[1]["source_labels"] == [
            'resourcequota']
        assert metric_relabel_config_search_result[1]["replacement"] == '$1'
        assert metric_relabel_config_search_result[1]["target_label"] == 'release'
