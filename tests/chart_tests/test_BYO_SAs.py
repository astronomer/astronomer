import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestServiceAccounts:
    def test_SAs_created(self, kube_version):
        docs = (render_chart(kube_version=kube_version, values={"global": {"rbacEnabled": False}}),)
        service_accounts = [
            doc["metadata"]["name"] for doc in docs if isinstance(doc, dict) and doc.get("kind") == "ServiceAccount"
        ]
        assert len(service_accounts) == 0
        # print(service_accounts)

    def test_role_created(self, kube_version):
        roles = []
        rolebindings = []
        docs = (render_chart(kube_version=kube_version, values={"global": {"rbacEnabled": False}}),)
        for doc in docs:
            if isinstance(doc, dict):
                if doc.get("kind") == "Role":
                    roles.append(doc["metadata"]["name"])
                elif doc.get("kind") == "RoleBinding":
                    rolebindings.append(doc["metadata"]["name"])
        assert len(roles) == 0
        assert len(rolebindings) == 0
