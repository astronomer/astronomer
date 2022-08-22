from tests.chart_tests.helm_template_generator import render_chart
import pytest
import base64
from tests import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestHoustonSecretHoustonRootAdminCredentials:
    def test_secret_root_admin_credentials_default_values(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"houston": {}}},
            show_only=[
                "charts/astronomer/templates/houston/api/houston-root-admin-secret.yaml"
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "Secret"
        username = base64.b64decode(doc["data"]["username"])

        assert username == b"root@example.com"
        assert len(base64.b64decode(doc["data"]["password"])) == 20
