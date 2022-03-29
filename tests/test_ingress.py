from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
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
            == "RELEASE-NAME-nginx"
        )

        # This would be valid python, but we load from json just to keep linters happy and the data more compact
        expected_rules_v1beta1 = json.loads(
            """
        [{"host":"example.com","http":{"paths":[{"path":"/","backend":{"serviceName":"RELEASE-NAME-astro-ui","servicePort":"astro-ui-http"}}]}},
        {"host":"app.example.com","http":{"paths":[{"path":"/","backend":{"serviceName":"RELEASE-NAME-astro-ui","servicePort":"astro-ui-http"}}]}},
        {"host":"registry.example.com","http":{"paths":[{"path":"/","backend":{"serviceName":"RELEASE-NAME-registry","servicePort":"registry-http"}}]}},
        {"host":"install.example.com","http":{"paths":[{"path":"/","backend":{"serviceName":"RELEASE-NAME-cli-install","servicePort":"install-http"}}]}}]
        """
        )
        expected_rules_v1 = json.loads(
            """
        [{"host":"example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"RELEASE-NAME-astro-ui","port":{"name":"astro-ui-http"}}}}]}},
        {"host":"app.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"RELEASE-NAME-astro-ui","port":{"name":"astro-ui-http"}}}}]}},
        {"host":"registry.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"RELEASE-NAME-registry","port":{"name":"registry-http"}}}}]}},
        {"host":"install.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"RELEASE-NAME-cli-install","port":{"name":"install-http"}}}}]}}]
        """
        )

        _, minor, _ = (int(x) for x in kube_version.split("."))

        if minor < 19:
            assert doc["apiVersion"] == "networking.k8s.io/v1beta1"
            assert doc["spec"]["rules"] == expected_rules_v1beta1
        else:
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert doc["spec"]["rules"] == expected_rules_v1
