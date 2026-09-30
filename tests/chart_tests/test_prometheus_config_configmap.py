import re

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
                    "prometheusPostgresExporter": {"enabled": True},
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
        assert any("foo-name-[cd]p-nginx" in str(regex) for regex in all_scrape_config_regexes)
        assert any("foo-name-postgresql-exporter" in str(regex) for regex in all_scrape_config_regexes)

    def test_prometheus_config_configmap_external_labels(self, kube_version):
        """Prometheus should have an external_labels section in config.yaml
        when external_labels is specified in helm values."""
        expected_labels = {"release": "release-name", "clusterid": "abc01", "external_labels_key_1": "external_labels_value_1"}
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "global": {"plane": {"domainPrefix": "abc01"}},
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
                "global": {"namespaceManagement": {"namespacePools": {"enabled": False}}},
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
                "global": {"namespaceManagement": {"namespaceFreeFormEntry": {"enabled": True}}},
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
                    "namespaceManagement": {
                        "namespacePools": {"enabled": True},
                        "namespaceFreeFormEntry": {"enabled": False},
                    },
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
                    "namespaceManagement": {"namespacePools": {"enabled": False}, "manualNamespaceNames": {"enabled": True}},
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

    def test_federated_dataplanes_default_scrape_settings(self, kube_version):
        """Test that federated-dataplanes uses default scrape_interval and scrape_timeout."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]
        federated = [s for s in scrape_configs if s["job_name"] == "federated-dataplanes"]

        assert len(federated) == 1
        assert federated[0]["scrape_interval"] == "15s"
        assert federated[0]["scrape_timeout"] == "10s"

    def test_federated_dataplanes_custom_scrape_settings(self, kube_version):
        """Test that federated-dataplanes scrape_interval and scrape_timeout are configurable."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
            values={
                "prometheus": {
                    "config": {
                        "scrape_configs": {
                            "federated_dataplanes": {
                                "scrape_interval": "30s",
                                "scrape_timeout": "5s",
                            },
                        },
                    },
                },
            },
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]
        federated = [s for s in scrape_configs if s["job_name"] == "federated-dataplanes"]

        assert len(federated) == 1
        assert federated[0]["scrape_interval"] == "30s"
        assert federated[0]["scrape_timeout"] == "5s"

    def test_federated_dataplanes_match_includes_operator_job(self, kube_version):
        """Operator-mode deployments scrape under job 'airflow-operator' on the data plane, while
        legacy Helm deployments use job 'airflow'. The federation selector is an anchored
        alternation, so 'airflow' matches only the legacy job — the operator job must be listed
        explicitly or its per-deployment metrics never federate to the control-plane Prometheus the
        Houston metrics UI queries. Regression guard for PLX-504 (operator-inheritance metrics)."""
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]
        federated = [s for s in scrape_configs if s["job_name"] == "federated-dataplanes"]
        assert len(federated) == 1

        match_selectors = federated[0]["params"]["match[]"]
        job_regex = re.search(r'job=~"([^"]+)"', match_selectors[0]).group(1)
        alternatives = job_regex.split("|")
        # Both the operator-mode job and the legacy Helm job must be federated, since both carry
        # per-deployment Airflow metrics the UI renders.
        assert "airflow-operator" in alternatives, alternatives
        assert "airflow" in alternatives, alternatives

    def test_prometheus_laminar_scrape_config(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
            values={"global": {"laminar": {"enabled": True}}},
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]
        laminar_hypervisor_scrape_config = [scrape for scrape in scrape_configs if scrape["job_name"] == "laminar-hypervisor"]
        laminar_api_server_scrape_config = [scrape for scrape in scrape_configs if scrape["job_name"] == "laminar-api-server"]
        assert len(laminar_hypervisor_scrape_config) == 1
        assert len(laminar_api_server_scrape_config) == 1

    def test_prometheus_laminar_scrape_config_disabled(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
            values={"global": {"laminar": {"enabled": False}}},
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]
        laminar_hypervisor_scrape_config = [scrape for scrape in scrape_configs if scrape["job_name"] == "laminar-hypervisor"]
        laminar_api_server_scrape_config = [scrape for scrape in scrape_configs if scrape["job_name"] == "laminar-api-server"]
        assert not laminar_hypervisor_scrape_config
        assert not laminar_api_server_scrape_config

    @pytest.mark.parametrize(
        ("mode", "scrape_targets", "expected_count"),
        [
            ("control", "nats_server", 1),
            ("unified", "nats_server", 1),
            ("data", "nats_server", 0),
        ],
    )
    def test_prometheus_nats_scrape_config(self, kube_version, mode, scrape_targets, expected_count):
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
            values={"global": {"plane": {"mode": mode}}},
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]
        nats_scrape_config = [scrape for scrape in scrape_configs if scrape["job_name"] == scrape_targets]
        assert len(nats_scrape_config) == expected_count

    @pytest.mark.parametrize(
        ("mode", "scrape_targets", "expected_count"),
        [
            ("control", "nginx", 1),
            ("unified", "nginx", 1),
            ("data", "nginx", 1),
        ],
    )
    def test_prometheus_nginx_scrape_config(self, kube_version, mode, scrape_targets, expected_count):
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            name="astronomer",
            values={"global": {"plane": {"mode": mode}}},
        )[0]
        scrape_configs = yaml.safe_load(doc["data"]["config"])["scrape_configs"]
        nginx_scrape_config = [scrape for scrape in scrape_configs if scrape["job_name"] == scrape_targets]
        assert len(nginx_scrape_config) == expected_count

    def get_cadvisor_job(self, kube_version):
        doc = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={"global": {"cadvisor": {"enabled": True}}},
        )[0]
        config = yaml.safe_load(doc["data"]["config"])
        cadvisor_jobs = jmespath.search("scrape_configs[?job_name == 'kubernetes-nodes-cadvisor']", config)
        assert len(cadvisor_jobs) == 1
        return cadvisor_jobs[0]

    def test_prometheus_cadvisor_deployment_relabel_resolves_worker_queue_pods(self, kube_version):
        """Worker Deployments are named `<release>-worker-<queue>`, one segment longer than
        other components' `<release>-<component>`, so a worker pod name is
        `<release>-worker-<queue>-<rs>-<pod>`. The `deployment` relabel must still resolve to
        `<release>` for these pods, for non-worker components, for a release name that itself
        contains dashes, and for a queue name that itself contains dashes (the CRD pattern
        `[a-z]([-a-z0-9]*[a-z0-9])?` permits e.g. "high-priority"). Regression guard for
        APC-1887 (WQ-25)."""
        cadvisor_job = self.get_cadvisor_job(kube_version)
        deployment_relabels = jmespath.search(
            "metric_relabel_configs[?target_label == 'deployment' && source_labels == ['pod_name']]",
            cadvisor_job,
        )
        assert len(deployment_relabels) == 1
        assert deployment_relabels[0]["replacement"] == "$1$2"

        pattern = re.compile(f"^(?:{deployment_relabels[0]['regex']})$")

        def resolve_deployment(pod_name):
            match = pattern.match(pod_name)
            assert match, f"pod_name {pod_name!r} did not match the deployment relabel regex"
            return "".join(group or "" for group in match.groups())

        assert resolve_deployment("myrelease-worker-default-7c9987ddf-ks7cv") == "myrelease"
        assert resolve_deployment("myrelease-worker-wq01-575dcd8686-vtfw2") == "myrelease"
        assert resolve_deployment("myrelease-worker-high-priority-7c9987ddf-ks7cv") == "myrelease"
        assert resolve_deployment("my-release-worker-default-7c9987ddf-ks7cv") == "my-release"
        assert resolve_deployment("myrelease-scheduler-675678c989-2cpqt") == "myrelease"
        assert resolve_deployment("myrelease-pgbouncer-5c9cfdbd5c-jlffk") == "myrelease"

    def test_prometheus_cadvisor_container_network_relabel_resolves_worker_queue_pods(self, kube_version):
        """The container_network_* relabels carry the same `<release>-<component>-<rs>-<pod>`
        positional assumption as the deployment relabel above, and must be fixed the same way
        for worker pods. Regression guard for APC-1887 (WQ-25)."""
        cadvisor_job = self.get_cadvisor_job(kube_version)
        network_relabels = jmespath.search(
            "metric_relabel_configs[?source_labels == ['__name__', 'container_name', 'pod_name']]",
            cadvisor_job,
        )
        assert len(network_relabels) == 3
        by_target = {relabel["target_label"]: relabel for relabel in network_relabels}
        assert set(by_target) == {"deployment", "component_name", "component_instance"}

        # all three relabels share the same regex; only the replacement differs
        regex = by_target["deployment"]["regex"]
        assert by_target["component_name"]["regex"] == regex
        assert by_target["component_instance"]["regex"] == regex
        pattern = re.compile(f"^(?:{regex})$")

        def resolve(pod_name, replacement):
            value = f"container_network_receive_bytes_total;POD;{pod_name}"
            match = pattern.match(value)
            assert match, f"{value!r} did not match the container_network relabel regex"
            result = replacement
            for index, group in enumerate(match.groups(), start=1):
                result = result.replace(f"${index}", group or "")
            return result

        for pod_name, expected_deployment, expected_component in [
            ("myrelease-worker-default-7c9987ddf-ks7cv", "myrelease", "worker"),
            ("myrelease-worker-wq01-575dcd8686-vtfw2", "myrelease", "worker"),
            ("myrelease-worker-high-priority-7c9987ddf-ks7cv", "myrelease", "worker"),
            ("my-release-worker-default-7c9987ddf-ks7cv", "my-release", "worker"),
            ("myrelease-scheduler-675678c989-2cpqt", "myrelease", "scheduler"),
        ]:
            assert resolve(pod_name, by_target["deployment"]["replacement"]) == expected_deployment
            assert resolve(pod_name, by_target["component_name"]["replacement"]) == expected_component
