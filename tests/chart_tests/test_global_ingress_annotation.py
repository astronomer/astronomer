from pathlib import Path

import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestGlobabIngressAnnotation:
    def test_global_ingress_with_astronomer_ingress(self, kube_version):
        """Test global ingress annotation for platform ingress."""

        all_ingress_files = [str(x.relative_to(git_root_dir)) for x in Path(git_root_dir).rglob("*ingress*.yaml")]

        always_rendered_ingress = [f for f in all_ingress_files if "external-es-proxy-ingress.yaml" not in f]
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"extraAnnotations": {"route.openshift.io/termination": "passthrough"}}},
            show_only=sorted(always_rendered_ingress),
        )
        assert len(docs) == 6
        for doc in docs:
            assert doc["kind"] == "Ingress"
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert "passthrough" in doc["metadata"]["annotations"]["route.openshift.io/termination"]
            assert len(doc["metadata"]["annotations"]) >= 4

        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "extraAnnotations": {"route.openshift.io/termination": "passthrough"},
                    "plane": {"mode": "data"},
                    "customLogging": {"enabled": True},
                },
                "astronomer": {"ingress": {"enabled": True}},
            },
            show_only=["charts/external-es-proxy/templates/external-es-proxy-ingress.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["kind"] == "Ingress"
        assert doc["apiVersion"] == "networking.k8s.io/v1"
        assert "passthrough" in doc["metadata"]["annotations"]["route.openshift.io/termination"]
        assert len(doc["metadata"]["annotations"]) >= 4
