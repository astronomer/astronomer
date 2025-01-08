import pytest
from tests import supported_k8s_versions, git_root_dir
from tests.chart_tests.helm_template_generator import render_chart
from pathlib import Path


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestGlobabIngressAnnotation:
    def test_global_ingress_with_astronomer_ingress(self, kube_version):
        """Test global ingress annotation for platform ingress ."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"extraAnnotations": {"route.openshift.io/termination": "passthrough"}}},
            show_only=sorted([str(x.relative_to(git_root_dir)) for x in Path(git_root_dir).rglob("*ingress*.yaml")]),
        )
        assert len(docs) == 6
        for doc in docs:
            assert doc["kind"] == "Ingress"
            assert doc["apiVersion"] == "networking.k8s.io/v1"
            assert "passthrough" in doc["metadata"]["annotations"]["route.openshift.io/termination"]
            assert len(doc["metadata"]["annotations"]) >= 4
