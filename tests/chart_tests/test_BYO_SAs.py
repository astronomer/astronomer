import pytest

from tests import supported_k8s_versions
from tests.chart_tests.helm_template_generator import render_chart

@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)

class TestServiceAccounts:
    def test_SAs_created(self, kube_version):
        docs = render_chart(
                kube_version=kube_version,
                values={"global": {"rbacEnabled": False}}),
        service_accounts=[]
        for doc in docs:
            if isinstance(doc, dict) and doc.get("kind") == "ServiceAccount":
                service_accounts.append(doc["metadata"]["name"])
        assert len(service_accounts) == 0
        #print(service_accounts)       


        




