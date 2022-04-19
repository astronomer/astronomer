from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import yaml


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestNSSelectorNetworkPolicies:
    def test_networkNSLabels_houston_configmap_with_feature_enabled(self, kube_version):
        """Test Houston Configmap with networkNSLabels."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"networkNSLabels": True}},
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "release-name-houston-config"
        assert prod["deployments"]["helm"]["networkNSLabels"] is True

    def test_networknsselector_with_postgresql(self, kube_version):
        """Test postgresql Service with namespace selector labels."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"networkNSLabels": True, "postgresqlEnabled": True}},
            show_only=[
                "charts/postgresql/templates/networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert "NetworkPolicy" == doc["kind"]
        assert [
            {
                "namespaceSelector": {"matchLabels": {"platform": "release-name"}},
                "podSelector": {"matchLabels": {"component": "pgbouncer"}},
            }
        ] == [doc["spec"]["ingress"][0]["from"][2]]
