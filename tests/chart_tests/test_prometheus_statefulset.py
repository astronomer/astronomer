from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions, get_containers_by_name


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusStatefulset:
    show_only = ["charts/prometheus/templates/prometheus-statefulset.yaml"]

    def test_prometheus_sts_basic_cases(self, kube_version):
        """Test some things that should apply to all cases."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
        )
        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-prometheus"
        assert len(doc["spec"]["template"]["spec"]["containers"]) == 2

        sc = doc["spec"]["template"]["spec"]["securityContext"]
        assert sc["fsGroup"] == 65534
        assert sc["runAsUser"] == 65534
        assert sc["runAsNonRoot"] is True

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["configmap-reloader"]["image"].startswith(
            "quay.io/astronomer/ap-configmap-reloader:"
        )
        assert c_by_name["configmap-reloader"]["volumeMounts"] == [
            {"mountPath": "/etc/prometheus/alerts.d", "name": "alert-volume"},
            {"mountPath": "/etc/prometheus/config", "name": "prometheus-config-volume"},
        ]
        assert c_by_name["prometheus"]["image"].startswith(
            "quay.io/astronomer/ap-prometheus:"
        )
        assert c_by_name["prometheus"]["ports"] == [
            {"containerPort": 9090, "name": "prometheus-data"}
        ]
        assert c_by_name["prometheus"]["volumeMounts"] == [
            {"mountPath": "/etc/prometheus/config", "name": "prometheus-config-volume"},
            {"mountPath": "/etc/prometheus/alerts.d", "name": "alert-volume"},
            {"mountPath": "/prometheus", "name": "data"},
        ]
        # check default liveness probe values
        assert c_by_name["prometheus"]["livenessProbe"]["initialDelaySeconds"] == 10
        assert c_by_name["prometheus"]["livenessProbe"]["periodSeconds"] == 5
        assert c_by_name["prometheus"]["livenessProbe"]["failureThreshold"] == 3
        assert c_by_name["prometheus"]["livenessProbe"]["timeoutSeconds"] == 1
        # check default readiness probe values
        assert c_by_name["prometheus"]["readinessProbe"]["initialDelaySeconds"] == 10
        assert c_by_name["prometheus"]["readinessProbe"]["periodSeconds"] == 5
        assert c_by_name["prometheus"]["readinessProbe"]["failureThreshold"] == 3
        assert c_by_name["prometheus"]["readinessProbe"]["timeoutSeconds"] == 1

    def test_prometheus_sts_override_probes(self, kube_version):
        """Test override of probe values."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
            values={
                "prometheus": {
                    "livenessProbe": {
                        "initialDelaySeconds": 20,
                        "periodSeconds": 21,
                        "failureThreshold": 22,
                        "timeoutSeconds": 15,
                    },
                    "readinessProbe": {
                        "initialDelaySeconds": 30,
                        "periodSeconds": 31,
                        "failureThreshold": 32,
                        "timeoutSeconds": 15,
                    },
                }
            },
        )
        assert len(docs) == 1
        doc = docs[0]

        c_by_name = get_containers_by_name(doc)
        # check modified liveness probe values
        assert c_by_name["prometheus"]["livenessProbe"]["initialDelaySeconds"] == 20
        assert c_by_name["prometheus"]["livenessProbe"]["periodSeconds"] == 21
        assert c_by_name["prometheus"]["livenessProbe"]["failureThreshold"] == 22
        assert c_by_name["prometheus"]["livenessProbe"]["timeoutSeconds"] == 15
        # check modified readiness probe values
        assert c_by_name["prometheus"]["readinessProbe"]["initialDelaySeconds"] == 30
        assert c_by_name["prometheus"]["readinessProbe"]["periodSeconds"] == 31
        assert c_by_name["prometheus"]["readinessProbe"]["failureThreshold"] == 32
        assert c_by_name["prometheus"]["readinessProbe"]["timeoutSeconds"] == 15

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
        print(c_by_name["prometheus"]["args"])
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
        print(c_by_name["prometheus"]["args"])
        assert (
            "--enable-feature=remote-write-receiver" in c_by_name["prometheus"]["args"]
        )
        assert "--enable-feature=agent" in c_by_name["prometheus"]["args"]
