from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions, get_containers_by_name


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusStatefulset:
    show_only = ["charts/prometheus/templates/prometheus-statefulset.yaml"]

    @staticmethod
    def prometheus_common_tests(doc):
        """Test common for prometheus statefulset."""
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-prometheus"

    def test_prometheus_sts_defaults(self, kube_version):
        """Test the default behavior of the prometheus statefulset."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
        )
        assert len(docs) == 1
        doc = docs[0]

        self.prometheus_common_tests(doc)
        assert len(doc["spec"]["template"]["spec"]["containers"]) == 2

        sc = doc["spec"]["template"]["spec"]["securityContext"]
        assert sc["fsGroup"] == 65534

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["configmap-reloader"]["image"].startswith("quay.io/astronomer/ap-configmap-reloader:")
        assert c_by_name["configmap-reloader"]["volumeMounts"] == [
            {"mountPath": "/etc/prometheus/alerts.d", "name": "alert-volume"},
            {"mountPath": "/etc/prometheus/config", "name": "prometheus-config-volume"},
        ]
        assert c_by_name["prometheus"]["image"].startswith("quay.io/astronomer/ap-prometheus:")
        assert c_by_name["prometheus"]["ports"] == [{"containerPort": 9090, "name": "prometheus-data"}]
        assert c_by_name["prometheus"]["volumeMounts"] == [
            {"mountPath": "/etc/prometheus/config", "name": "prometheus-config-volume"},
            {"mountPath": "/etc/prometheus/alerts.d", "name": "alert-volume"},
            {"mountPath": "/prometheus", "name": "data"},
        ]
        assert "persistentVolumeClaimRetentionPolicy" not in doc["spec"]
        assert c_by_name["prometheus"]["livenessProbe"]["initialDelaySeconds"] == 10
        assert c_by_name["prometheus"]["livenessProbe"]["periodSeconds"] == 5
        assert c_by_name["prometheus"]["livenessProbe"]["failureThreshold"] == 3
        assert c_by_name["prometheus"]["livenessProbe"]["timeoutSeconds"] == 1
        assert c_by_name["prometheus"]["readinessProbe"]["initialDelaySeconds"] == 10
        assert c_by_name["prometheus"]["readinessProbe"]["periodSeconds"] == 5
        assert c_by_name["prometheus"]["readinessProbe"]["failureThreshold"] == 3
        assert c_by_name["prometheus"]["readinessProbe"]["timeoutSeconds"] == 1
        assert "priorityClassName" not in doc["spec"]["template"]["spec"]

    def test_prometheus_with_extraFlags(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "prometheus": {"extraFlags": ["--log.level=debug"]},
            },
            show_only=["charts/prometheus/templates/prometheus-statefulset.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert "--log.level=debug" in c_by_name["prometheus"]["args"]

    def test_prometheus_with_multiple_extraFlags(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "prometheus": {
                    "extraFlags": [
                        "--enable-feature=remote-write-receiver",
                        "--enable-feature=agent",
                    ]
                },
            },
            show_only=["charts/prometheus/templates/prometheus-statefulset.yaml"],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert "--enable-feature=remote-write-receiver" in c_by_name["prometheus"]["args"]
        assert "--enable-feature=agent" in c_by_name["prometheus"]["args"]

    def test_prometheus_persistentVolumeClaimRetentionPolicy(self, kube_version):
        test_persistentVolumeClaimRetentionPolicy = {
            "whenDeleted": "Delete",
            "whenScaled": "Retain",
        }
        doc = render_chart(
            kube_version=kube_version,
            values={
                "prometheus": {
                    "persistence": {
                        "persistentVolumeClaimRetentionPolicy": test_persistentVolumeClaimRetentionPolicy,
                    },
                },
            },
            show_only=["charts/prometheus/templates/prometheus-statefulset.yaml"],
        )[0]

        assert "persistentVolumeClaimRetentionPolicy" in doc["spec"]
        assert test_persistentVolumeClaimRetentionPolicy == doc["spec"]["persistentVolumeClaimRetentionPolicy"]

    def test_prometheus_service_account_overrides(self, kube_version):
        """Test the prometheus do not render service account and rbac when global rbac is true and prometheus service account create is false."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "prometheus": {
                    "serviceAccount": {
                        "create": False,
                    },
                },
            },
            show_only=["charts/prometheus/templates/prometheus-statefulset.yaml"],
        )

        assert len(docs) == 1
        assert "default" in docs[0]["spec"]["template"]["spec"]["serviceAccountName"]

    def test_prometheus_with_global_nodepool_config(self, kube_version, global_platform_node_pool_config):
        """Test Prometheus with nodeSelector, affinity, tolerations and global config."""
        values = {
            "global": {
                "platformNodePool": global_platform_node_pool_config,
            }
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/prometheus/templates/prometheus-statefulset.yaml",
            ],
        )

        assert len(docs) == 1
        self.prometheus_common_tests(docs[0])
        spec = docs[0]["spec"]["template"]["spec"]
        assert spec["nodeSelector"]["role"] == "astro"
        assert len(spec["affinity"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["global"]["platformNodePool"]["tolerations"]

    def test_prometheus_platform_nodepool_subchart_overrides(self, kube_version, global_platform_node_pool_config):
        """Test Prometheus with nodeSelector, affinity, tolerations and subchart config overrides."""
        global_platform_node_pool_config["nodeSelector"] = {"role": "astroprometheus"}
        values = {
            "prometheus": {
                "nodeSelector": global_platform_node_pool_config["nodeSelector"],
                "affinity": global_platform_node_pool_config["affinity"],
                "tolerations": global_platform_node_pool_config["tolerations"],
            },
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/prometheus/templates/prometheus-statefulset.yaml"],
        )

        assert len(docs) == 1
        self.prometheus_common_tests(docs[0])
        spec = docs[0]["spec"]["template"]["spec"]
        assert spec["nodeSelector"]["role"] == "astroprometheus"
        assert len(spec["affinity"]) == 1
        assert len(spec["tolerations"]) > 0
        assert spec["tolerations"] == values["prometheus"]["tolerations"]

    def test_prometheus_filesd_reloader_enabled(self, kube_version):
        """Test Prometheus with filesd reloader enabled."""
        values = {
            "global": {"rbacEnabled": False},
            "prometheus": {},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/prometheus/templates/prometheus-statefulset.yaml"],
        )

        assert len(docs) == 1
        self.prometheus_common_tests(docs[0])
        c_by_name = get_containers_by_name(docs[0])
        env_vars = {x["name"]: x.get("value", x.get("valueFrom")) for x in c_by_name["filesd-reloader"]["env"]}
        assert env_vars["DATABASE_SCHEMA_NAME"] == "houston$default"
        assert env_vars["DEPLOYMENT_TABLE_NAME"] == "Deployment"
        assert env_vars["DATABASE_NAME"] == "release-name_houston"
        assert env_vars["FILESD_FILE_PATH"] == "/prometheusreloader/airflow"
        assert env_vars["ENABLE_DEPLOYMENT_SCRAPING"] == "true"
        assert env_vars["ENABLE_CLUSTER_SCRAPING"] == "false"
        assert c_by_name["filesd-reloader"]["volumeMounts"] == [{"mountPath": "/prometheusreloader/airflow", "name": "filesd"}]

    def test_prometheus_filesd_reloader_extraenv_enabled(self, kube_version):
        """Test Prometheus with filesd reloader enabled with extraenv overrides."""
        values = {
            "global": {"rbacEnabled": False},
            "prometheus": {"filesdReloader": {"extraEnv": [{"name": "CUSTOM_DATABASE_NAME", "values": "astrohouston"}]}},
        }
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/prometheus/templates/prometheus-statefulset.yaml"],
        )

        assert len(docs) == 1
        self.prometheus_common_tests(docs[0])
        c_by_name = get_containers_by_name(docs[0])
        assert {"name": "CUSTOM_DATABASE_NAME", "values": "astrohouston"} in c_by_name["filesd-reloader"]["env"]

    def test_prometheus_cluster_role_defaults(self, kube_version):
        """Test Prometheus with cluster role defaults."""
        values = {}
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/prometheus/templates/prometheus-role.yaml",
                "charts/prometheus/templates/prometheus-rolebinding.yaml",
            ],
        )

        assert len(docs) == 2
        assert docs[0]["kind"] == "ClusterRole"
        assert docs[1]["kind"] == "ClusterRoleBinding"

    def test_prometheus_cluster_role_overrides(self, kube_version):
        """Test Prometheus with role and rolebinding."""
        values = {"global": {"rbacEnabled": True}, "prometheus": {"rbac": {"role": {"kind": "Role", "create": True}}}}
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=[
                "charts/prometheus/templates/prometheus-role.yaml",
                "charts/prometheus/templates/prometheus-rolebinding.yaml",
            ],
        )

        assert len(docs) == 2
        assert docs[0]["kind"] == "Role"
        assert docs[1]["kind"] == "RoleBinding"

    def test_prometheus_priorityclass_overrides(self, kube_version):
        """Test to validate prometheus with priority class configured."""
        docs = render_chart(
            kube_version=kube_version,
            values={"prometheus": {"priorityClassName": "prometheus-priority-pod"}},
            show_only=["charts/prometheus/templates/prometheus-statefulset.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        self.prometheus_common_tests(docs[0])
        spec = doc["spec"]["template"]["spec"]
        assert "priorityClassName" in spec
        assert "prometheus-priority-pod" == spec["priorityClassName"]
