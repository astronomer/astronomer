import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusService:
    show_only = ["charts/prometheus/templates/prometheus-service.yaml"]

    def aggregate_service(self, kube_version, values=None):
        """Render and return the aggregate (load-balancing) prometheus Service."""
        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=self.show_only,
        )
        aggregate = [d for d in docs if d["metadata"]["name"] == "release-name-prometheus"]
        assert len(aggregate) == 1
        doc = aggregate[0]
        assert doc["kind"] == "Service"
        return doc

    def test_no_session_affinity_by_default(self, kube_version):
        """sessionAffinity must be absent by default so the rendered Service carries no
        spec.sessionAffinity / sessionAffinityConfig (forbidden by e.g. Gatekeeper's
        deny-ingress-sticky-sessions). See PINF-692."""
        # default install is replicas=1, so the aggregate Service is the only doc
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Service"
        assert doc["metadata"]["name"] == "release-name-prometheus"
        assert doc["spec"]["type"] == "ClusterIP"
        assert "sessionAffinity" not in doc["spec"]
        assert "sessionAffinityConfig" not in doc["spec"]

    def test_session_affinity_opt_in(self, kube_version):
        """Setting prometheus.sessionAffinity restores the field for multi-replica HA."""
        doc = self.aggregate_service(
            kube_version,
            values={"prometheus": {"sessionAffinity": "ClientIP"}},
        )
        assert doc["spec"]["sessionAffinity"] == "ClientIP"
