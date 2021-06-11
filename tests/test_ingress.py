from tests.helm_template_generator import render_chart
import jmespath
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestIngress:
    def test_should_pass_validation_with_just_ingress_enabled(self, kube_version):
        render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/ingress.yaml"],
        )  # checks that no validation exception is raised

    def test_should_allow_more_than_one_annotation(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/ingress.yaml"],
        )
        assert (
            jmespath.search("metadata.annotations", docs[0])[
                "kubernetes.io/ingress.class"
            ]
            == "RELEASE-NAME-nginx"
        )
