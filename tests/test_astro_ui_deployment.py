from tests.helm_template_generator import render_chart
import jmespath


def test_astro_ui_deployment():
    docs = render_chart(
        values={
            "astronomer": {
                "astroUI": {
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "256Mi"},
                        "limits": {"cpu": "500m", "memory": "1024Mi"},
                    }
                }
            }
        },
        show_only=["charts/astronomer/templates/astro-ui/astro-ui-deployment.yaml"],
    )

    assert "Deployment" == jmespath.search("kind", docs[0])
    assert "RELEASE-NAME-astro-ui" == jmespath.search("metadata.name", docs[0])
    assert "astro-ui" == jmespath.search(
        "spec.template.spec.containers[0].name", docs[0]
    )
    assert "500m" == jmespath.search(
        "spec.template.spec.containers[0].resources.limits.cpu", docs[0]
    )
