from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import json


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestIngress:
    def test_basic_ingress(self, kube_version):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/ingress.yaml"],
        )

        assert len(docs) == 1

        doc = docs[0]

        assert doc["kind"] == "Ingress"

        assert len(doc["metadata"]["annotations"]) >= 4
        assert (
            doc["metadata"]["annotations"]["kubernetes.io/ingress.class"]
            == "release-name-nginx"
        )

        expected_rules_v1 = json.loads(
            """
        [{"host":"example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}},
        {"host":"app.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}},
        {"host":"registry.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"release-name-registry","port":{"name":"registry-http"}}}}]}},
        {"host":"install.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"release-name-cli-install","port":{"name":"install-http"}}}}]}}]
        """
        )

        assert doc["apiVersion"] == "networking.k8s.io/v1"
        assert doc["spec"]["rules"] == expected_rules_v1
