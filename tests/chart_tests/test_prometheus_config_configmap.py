from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import yaml


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusConfigConfigmap:
    show_only = ["charts/prometheus/templates/prometheus-config-configmap.yaml"]

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

        # config_yaml = doc["data"]["config"]
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

    def test_prometheus_config_configmap_scrape_interval(self, kube_version):
        """Prometheus should have configurable scrape interval duration which
        can be defined as helm value."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "prometheus": {
                    "scrape_interval": "30s",
                    "evaluation_interval": "foo",
                    "velero": {"scrape_interval": "velero"},
                    "fluentd": {"scrape_interval": "fluentd"},
                    "airflow": {"scrape_interval": "airflow"},
                    "nodeExporter": {"scrape_interval": "node-exp"},
                    "kubeState": {"scrape_interval": "kube-state"},
                    "postgresqlExporter": {
                        "scrape_interval": "foo",
                        "scrape_timeout": "bar",
                    },
                }
            },
        )[0]
        # few jobs have scrape timeout, that's why dirty if-else
        config_yaml = yaml.safe_load(doc["data"]["config"])
        assert config_yaml["global"]["scrape_interval"] == "30s"
        assert config_yaml["global"]["evaluation_interval"] == "foo"
        for job in config_yaml["scrape_configs"]:
            if job["job_name"] == "velero":
                assert job["scrape_interval"] == "velero"
            elif job["job_name"] == "fluentd":
                assert job["scrape_interval"] == "fluentd"
            elif job["job_name"] == "airflow":
                assert job["scrape_interval"] == "airflow"
            elif job["job_name"] == "node-exporter":
                assert job["scrape_interval"] == "node-exp"
            elif job["job_name"] == "kube-state":
                assert job["scrape_interval"] == "kube-state"
            if job["job_name"] == "postgresql-exporter":
                assert job["scrape_interval"] == "foo"
                assert job["scrape_timeout"] == "bar"

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
                "prometheus": {
                    "nodeExporter": {"scrape_interval": "333s"},
                },
            },
        )[0]

        nodeExporterConfigs = [
            x
            for x in yaml.safe_load(doc["data"]["config"])["scrape_configs"]
            if x["job_name"] == "node-exporter"
        ]
        assert nodeExporterConfigs[0]["scrape_interval"] == "333s"

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
