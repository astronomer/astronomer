from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions, get_containers_by_name


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
        assert doc["metadata"]["name"] == "RELEASE-NAME-prometheus"
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
