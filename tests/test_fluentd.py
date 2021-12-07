from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_fluentd_clusterrolebinding(kube_version):
    """Test that helm renders a good ClusterRoleBinding template for fluentd when rbacEnabled=True."""
    docs = render_chart(
        kube_version=kube_version,
        values={"global": {"rbacEnabled": True}},
        show_only=["charts/fluentd/templates/fluentd-clusterrolebinding.yaml"],
    )

    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "ClusterRoleBinding"
    assert doc["apiVersion"] == "rbac.authorization.k8s.io/v1"
    assert doc["metadata"]["name"] == "RELEASE-NAME-fluentd"
    assert len(doc["roleRef"]) > 0
    assert len(doc["subjects"]) > 0

    docs = render_chart(
        kube_version=kube_version,
        values={"global": {"rbacEnabled": False}},
        show_only=["charts/fluentd/templates/fluentd-clusterrolebinding.yaml"],
    )

    assert len(docs) == 0
