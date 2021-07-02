from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import jmespath


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
def test_fluentd_daemonset(kube_version):
    """Test that helm renders a volume mount for private ca certificates for fluentd daemonset when private-ca-certificates are enabled."""
    docs = render_chart(
        kube_version=kube_version,
        values={"global": {"privateCaCerts": ["private-root-ca"]}},
        show_only=["charts/fluentd/templates/fluentd-daemonset.yaml"],
    )

    search_result = jmespath.search(
        "spec.template.spec.containers[*].volumeMounts[?name == 'private-root-ca']",
        docs[0],
    )
    expected_result = [
        [
            {
                "mountPath": "/usr/local/share/ca-certificates/private-root-ca.pem",
                "name": "private-root-ca",
                "subPath": "cert.pem",
            }
        ]
    ]
    assert search_result == expected_result


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
