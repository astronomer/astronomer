import jmespath
import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

prometheus_job = {
    "job_name": "prometheus",
    "static_configs": [{"targets": ["localhost:9090"]}],
}

airflow_scrape_relabel_config = [
    {"action": "labelmap", "regex": "__meta_kubernetes_service_label_(.+)"},
    {
        "source_labels": ["__meta_kubernetes_service_label_astronomer_io_platform_release"],
        "regex": "^astronomer$",
        "action": "keep",
    },
    {"source_labels": ["__meta_kubernetes_service_annotation_prometheus_io_scrape"], "action": "keep", "regex": True},
    {
        "source_labels": ["__address__", "__meta_kubernetes_service_annotation_prometheus_io_port"],
        "action": "replace",
        "regex": "([^:]+)(?::\\d+)?;(\\d+)",
        "replacement": "$1:$2",
        "target_label": "__address__",
    },
]


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

        config_yaml = yaml.safe_load(doc["data"]["config"])
        houston_jobs = [x for x in config_yaml["scrape_configs"] if x["job_name"] == "houston-api"]
        assert len(houston_jobs) == 1
        assert houston_jobs[0]["metrics_path"] == "/v1/metrics"

    def test_prometheus_config_configmap_with_different_name_and_ns(self, kube_version):
        """Validate the prometheus config configmap does not conflate deployment name and namespace."""
        doc = render_chart(
            name="foo-name",
            namespace="bar-ns",
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "prometheusPostgresExporterEnabled": True,
                },
            },
        )[0]

        config_yaml = yaml.safe_load(doc["data"]["config"])
        all_scrape_config_namespaces = {
            ns_name
            for x in config_yaml["scrape_configs"]
            for y in x.get("kubernetes_sd_configs", [])
            for ns_name in y.get("namespaces", {}).get("names", [])
        }

        assert "bar-ns" in all_scrape_config_namespaces
        assert "foo-name" not in all_scrape_config_namespaces

        all_scrape_config_regexes = {
            y.get("regex", "") for x in config_yaml["scrape_configs"] for y in x.get("relabel_configs", [])
        }

        # These assertions only work because we know that namespaces do not show up in our configured regexes.
        assert "bar-ns" not in all_scrape_config_regexes
        assert any("foo-name-houston" in str(regex) for regex in all_scrape_config_regexes)
        assert any("foo-name-nginx" in str(regex) for regex in all_scrape_config_regexes)
        assert any("foo-name-postgresql-exporter" in str(regex) for regex in all_scrape_config_regexes)

    def test_prometheus_config_configmap_external_labels(self, kube_version):
        """Prometheus should have an external_labels section in config.yaml
        when external_labels is specified in helm values."""
        expected_labels = {"release": "release-name", "clusterid": "abc01", "external_labels_key_1": "external_labels_value_1"}
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {"plane": {"domainSuffix": "abc01"}},
                "prometheus": {
                    "external_labels": expected_labels,
                },
            },
        )[0]

        config_yaml = yaml.safe_load(doc["data"]["config"])
        assert config_yaml["global"]["external_labels"] == expected_labels

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

    def test_prometheus_config_release_relabel(self, kube_version):
        """Prometheus should have a regex for release name."""
        namespace = "testnamespace"
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            namespace=namespace,
            values={
                "global": {"features": {"namespacePools": {"enabled": False}}},
                "astronomer": {
                    "houston": {
                        "config": {"deployments": {"namespaceFreeFormEntry": False}},
                    },
                },
            },
        )[0]

        config = yaml.safe_load(doc["data"]["config"])
        scrape_config_search_result = jmespath.search("scrape_configs[?job_name == 'kube-state']", config)
        metric_relabel_config_search_result = jmespath.search(
            "metric_relabel_configs[?target_label == 'release']",
            scrape_config_search_result[0],
        )

        assert len(metric_relabel_config_search_result) == 1
        assert metric_relabel_config_search_result[0]["source_labels"] == ["namespace"]
        assert metric_relabel_config_search_result[0]["regex"] == "^testnamespace-(.*$)"
        assert metric_relabel_config_search_result[0]["replacement"] == "$1"
        assert metric_relabel_config_search_result[0]["target_label"] == "release"

    def test_prometheus_config_release_relabel_with_free_from_namespace(self, kube_version):
        """Prometheus should not have a regex for release name when free form
        namespace is enabled."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {"namespaceFreeFormEntry": True},
            },
        )[0]
        self.assert_relabel_config_for_non_auto_generated_namesaces(doc)

    def test_prometheus_config_insecure_skip_verify(self, kube_version):
        """Test that insecure_skip_verify is rendered correctly in the config when specified."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "prometheus": {
                    "config": {"scrape_configs": {"kubernetes_apiservers": {"tls_config": {"insecure_skip_verify": True}}}},
                },
            },
        )[0]

        config_yaml = yaml.safe_load(doc["data"]["config"])
        assert [
            x["tls_config"]["insecure_skip_verify"]
            for x in list(config_yaml["scrape_configs"])
            if x["job_name"] == "kubernetes-apiservers"
        ] == [True]

    def test_prometheus_config_release_relabel_with_pre_created_namespace(self, kube_version):
        """Prometheus should have a regex for release name when namespacePools
        namespace is enabled."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "features": {"namespacePools": {"enabled": True}},
                    "namespaceFreeFormEntry": False,
                }
            },
        )[0]
        self.assert_relabel_config_for_non_auto_generated_namesaces(doc)

    def test_prometheus_config_release_relabel_with_manual_namespace_names_enabled(self, kube_version):
        """Prometheus should have a regex for release name when manualNamespaceNames
        is enabled."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {
                    "features": {"namespacePools": {"enabled": False}},
                    "manualNamespaceNamesEnabled": True,
                }
            },
        )[0]
        self.assert_relabel_config_for_non_auto_generated_namesaces(doc)

    def assert_relabel_config_for_non_auto_generated_namesaces(self, chart):
        config = yaml.safe_load(chart["data"]["config"])
        scrape_config_search_result = jmespath.search("scrape_configs[?job_name == 'kube-state']", config)
        metric_relabel_config_search_result = jmespath.search(
            "metric_relabel_configs[?target_label == 'release']",
            scrape_config_search_result[0],
        )
        assert len(metric_relabel_config_search_result) == 2
        assert (
            metric_relabel_config_search_result[0]["regex"]
            == "(.*?)(?:-webserver.*|-api-server.*|-scheduler.*|-worker.*|-cleanup.*|-pgbouncer.*|-statsd.*|-triggerer.*|-run-airflow-migrations.*|-git-sync-relay.*)?$"
        )
        assert metric_relabel_config_search_result[0]["source_labels"] == ["pod"]
        assert metric_relabel_config_search_result[0]["replacement"] == "$1"
        assert metric_relabel_config_search_result[0]["target_label"] == "release"

        assert metric_relabel_config_search_result[1]["regex"] == "(.+)-resource-quota$"
        assert metric_relabel_config_search_result[1]["source_labels"] == ["resourcequota"]
        assert metric_relabel_config_search_result[1]["replacement"] == "$1"
        assert metric_relabel_config_search_result[1]["target_label"] == "release"

    def test_additional_scrape_jobs(self, kube_version):
        static_job = {
            "job_name": "example-static-job",
            "static_configs": [{"targets": ["localhost:9090"]}],
        }
        kubernetes_job = {
            "job_name": "example-kubernetes-job",
            "kubernetes_sd_configs": [
                {
                    "role": "endpoints",
                    "namespaces": {"names": ["default"]},
                }
            ],
        }
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
            values={
                "prometheus": {
                    "additionalScrapeJobs": [
                        static_job,
                        kubernetes_job,
                    ]
                }
            },
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]

        assert static_job in scrape_configs, "Static job not found in rendered ConfigMap"
        assert kubernetes_job in scrape_configs, "Kubernetes job not found in rendered ConfigMap"

    def test_prometheus_self_scrape_config_feature_defaults(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
            values={"prometheus": {"config": {"enableSelfScrape": True}}},
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]

        assert prometheus_job in scrape_configs, "prometheus job not found in rendered ConfigMap"

    def test_prometheus_self_scrape_config_feature_disabled(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
            values={"prometheus": {"config": {"enableSelfScrape": False}}},
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]

        assert prometheus_job not in scrape_configs

    def test_prometheus_operator_integration_config(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
            values={"global": {"airflowOperator": {"enabled": True}}},
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]
        airflow_operator_scrape_config = [scrape for scrape in scrape_configs if scrape["job_name"] == "airflow-operator"]
        for index in range(len(airflow_scrape_relabel_config)):
            expected = airflow_scrape_relabel_config[index]
            actual = airflow_operator_scrape_config[0]["relabel_configs"][index]
            assert expected == actual

    def test_prometheus_operator_integration_config_disabled(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
            values={"global": {"airflowOperator": {"enabled": False}}},
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]
        airflow_operator_scrape_config = [scrape for scrape in scrape_configs if scrape["job_name"] == "airflow-operator"]
        assert len(airflow_operator_scrape_config) == 0

    def test_prometheus_operator_integration_config_disabled_with_no_cluster_role(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
            values={"global": {"airflowOperator": {"enabled": True}, "clusterRoles": False}},
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]
        airflow_operator_scrape_config = [scrape for scrape in scrape_configs if scrape["job_name"] == "airflow-operator"]
        assert len(airflow_operator_scrape_config) == 0
        airflow_scrape_config = [scrape for scrape in scrape_configs if scrape["job_name"] == "airflow"]
        assert len(airflow_scrape_config) == 1
