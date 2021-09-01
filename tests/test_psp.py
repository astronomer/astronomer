from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
from subprocess import CalledProcessError


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPspEnabled:
    psp_docs = [
        {
            "template": "charts/elasticsearch/templates/es-psp.yaml",
            "name": "RELEASE-NAME-elasticsearch",
        },
        {
            "template": "charts/fluentd/templates/fluentd-psp.yaml",
            "name": "RELEASE-NAME-fluentd",
        },
        {
            "template": "charts/nginx/templates/nginx-psp.yaml",
            "name": "RELEASE-NAME-ingress-nginx",
        },
        {
            "template": "charts/prometheus-node-exporter/templates/psp.yaml",
            "name": "RELEASE-NAME-prometheus-node-exporter",
        },
        {
            "template": "templates/psp/permissive-psp.yaml",
            "name": "RELEASE-NAME-permissive",
        },
        {
            "template": "templates/psp/restrictive-psp.yaml",
            "name": "RELEASE-NAME-restrictive",
        },
    ]

    psp_doc_ids = [x["template"] for x in psp_docs]

    @pytest.mark.parametrize("psp_docs", psp_docs, ids=psp_doc_ids)
    def test_psp(self, kube_version, psp_docs):
        """Test that helm errors when pspEnabled=False, and renders a good PodSecurityPolicy template when pspEnabled=True."""
        with pytest.raises(CalledProcessError):
            docs = render_chart(
                kube_version=kube_version,
                values={"global": {"pspEnabled": False}},
                show_only=[psp_docs["template"]],
            )

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"pspEnabled": True}},
            show_only=[psp_docs["template"]],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "PodSecurityPolicy"
        assert doc["apiVersion"] == "policy/v1beta1"
        assert doc["metadata"]["name"] == psp_docs["name"]
        assert "spec" in doc

    clusterrole_docs = [
        {
            "template": "charts/elasticsearch/templates/es-psp-clusterrole.yaml",
            "name": "RELEASE-NAME-psp-elasticsearch",
        },
        {
            "template": "charts/fluentd/templates/fluentd-psp-clusterrole.yaml",
            "name": "RELEASE-NAME-psp-fluentd",
        },
        {
            "template": "charts/nginx/templates/nginx-psp-clusterrole.yaml",
            "name": "RELEASE-NAME-psp-ingress-nginx",
        },
        {
            "template": "charts/prometheus-node-exporter/templates/psp-clusterrole.yaml",
            "name": "psp-RELEASE-NAME-prometheus-node-exporter",
        },
        {
            "template": "templates/psp/permissive-clusterrole.yaml",
            "name": "RELEASE-NAME-psp-permissive",
        },
        {
            "template": "templates/psp/restrictive-clusterrole.yaml",
            "name": "RELEASE-NAME-psp-restrictive",
        },
    ]

    clusterrole_doc_ids = [x["template"] for x in clusterrole_docs]

    @pytest.mark.parametrize(
        "clusterrole_docs", clusterrole_docs, ids=clusterrole_doc_ids
    )
    def test_clusterrole(self, kube_version, clusterrole_docs):
        """Test that helm errors when pspEnabled=False, and renders a good ClusterRole template when pspEnabled=True."""
        with pytest.raises(CalledProcessError):
            docs = render_chart(
                kube_version=kube_version,
                values={"global": {"pspEnabled": False}},
                show_only=[clusterrole_docs["template"]],
            )

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"pspEnabled": True}},
            show_only=[clusterrole_docs["template"]],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ClusterRole"
        assert doc["apiVersion"] == "rbac.authorization.k8s.io/v1beta1"
        assert doc["metadata"]["name"] == clusterrole_docs["name"]
        assert "rules" in doc
        assert all(
            item in doc["rules"][0]
            for item in ["apiGroups", "resources", "resourceNames", "verbs"]
        )

    clusterrolebinding_docs = [
        {
            "template": "charts/prometheus-node-exporter/templates/psp-clusterrolebinding.yaml",
            "name": "psp-RELEASE-NAME-prometheus-node-exporter",
        },
        {
            "template": "templates/psp/restrictive-cluserrolebinding.yaml",
            "name": "RELEASE-NAME-psp-restrictive",
        },
    ]

    clusterrolebinding_doc_ids = [x["template"] for x in clusterrolebinding_docs]

    @pytest.mark.parametrize(
        "clusterrolebinding_docs",
        clusterrolebinding_docs,
        ids=clusterrolebinding_doc_ids,
    )
    def test_clusterrolebinding(self, kube_version, clusterrolebinding_docs):
        """Test that helm errors when pspEnabled=False, and renders a good ClusterRoleBinding template when pspEnabled=True."""
        with pytest.raises(CalledProcessError):
            docs = render_chart(
                kube_version=kube_version,
                values={"global": {"pspEnabled": False}},
                show_only=[clusterrolebinding_docs["template"]],
            )

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"pspEnabled": True}},
            show_only=[clusterrolebinding_docs["template"]],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "ClusterRoleBinding"
        assert doc["apiVersion"] == "rbac.authorization.k8s.io/v1beta1"
        assert doc["metadata"]["name"] == clusterrolebinding_docs["name"]
        assert len(doc["roleRef"]) >= 1
        assert len(doc["subjects"]) >= 1

    rolebinding_docs = [
        {
            "template": "charts/elasticsearch/templates/es-psp-rolebinding.yaml",
            "name": "RELEASE-NAME-psp-elasticsearch",
        },
        {
            "template": "charts/fluentd/templates/fluentd-psp-rolebinding.yaml",
            "name": "RELEASE-NAME-psp-fluentd",
        },
        {
            "template": "charts/nginx/templates/nginx-psp-rolebinding.yaml",
            "name": "RELEASE-NAME-psp-ingress-nginx",
        },
        {
            "template": "templates/psp/permissive-clusterrolebinding.yaml",
            "name": "RELEASE-NAME-psp-permissive",
        },
    ]

    rolebinding_doc_ids = [x["template"] for x in rolebinding_docs]

    @pytest.mark.parametrize(
        "rolebinding_docs",
        rolebinding_docs,
        ids=rolebinding_doc_ids,
    )
    def test_rolebinding(self, kube_version, rolebinding_docs):
        """Test that helm errors when pspEnabled=False, and renders a good RoleBinding template when pspEnabled=True."""
        with pytest.raises(CalledProcessError):
            docs = render_chart(
                kube_version=kube_version,
                values={"global": {"pspEnabled": False}},
                show_only=[rolebinding_docs["template"]],
            )

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"pspEnabled": True}},
            show_only=[rolebinding_docs["template"]],
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "RoleBinding"
        assert doc["apiVersion"] == "rbac.authorization.k8s.io/v1beta1"
        assert doc["metadata"]["name"] == rolebinding_docs["name"]
        assert len(doc["roleRef"]) >= 1
        assert len(doc["subjects"]) >= 1
