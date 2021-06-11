from tests.helm_template_generator import render_chart
import jmespath
import pytest


@pytest.mark.parametrize(
    "kube_version",
    ["1.16.0", "1.17.0", "1.18.0", "1.19.0", "1.20.0", "1.21.0"],
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
