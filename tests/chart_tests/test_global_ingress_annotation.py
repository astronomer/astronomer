from pathlib import Path

import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestGlobabIngressAnnotation:
    def test_global_ingress_with_astronomer_ingress(self, kube_version):
        """Test global ingress annotation for platform ingress."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"extraAnnotations": {"route.openshift.io/termination": "passthrough"}}},
            show_only=sorted([str(x.relative_to(git_root_dir)) for x in Path(git_root_dir).rglob("*ingress*.yaml")]),
        )
        assert len(docs) == 7
        ingress_docs = [doc for doc in docs if doc["kind"] == "Ingress"]
        ingress_class_docs = [doc for doc in docs if doc["kind"] == "IngressClass"]
        assert len(ingress_docs) >= 1
        assert len(ingress_class_docs) >= 1
        for doc in ingress_docs:
            assert doc["kind"] == "Ingress"
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            annotations = doc["metadata"].get("annotations", {})
            if annotations:
                assert "kubernetes.io/ingress.class" not in annotations
                if "route.openshift.io/termination" in annotations:
                    assert "passthrough" in annotations["route.openshift.io/termination"]

        for doc in ingress_class_docs:
            assert doc["kind"] == "IngressClass"
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert "controller" in doc["spec"]