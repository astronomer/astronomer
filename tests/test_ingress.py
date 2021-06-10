from tests.helm_template_generator import render_chart
import jmespath


def test_should_pass_validation_with_just_ingress_enabled():
    render_chart(
        show_only=["charts/astronomer/templates/ingress.yaml"],
    )  # checks that no validation exception is raised


def test_should_allow_more_than_one_annotation():
    docs = render_chart(
        show_only=["charts/astronomer/templates/ingress.yaml"],
    )
    assert (
        jmespath.search("metadata.annotations", docs[0])["kubernetes.io/ingress.class"]
        == "RELEASE-NAME-nginx"
    )
