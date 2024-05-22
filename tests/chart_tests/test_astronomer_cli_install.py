from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions
import jmespath


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerCliInstall:
    def test_astronomer_cli_install_default(self, kube_version):
        """Test that helm renders a good deployment template for
        astronomer/cli-install."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/cli-install/cli-install-configmap.yaml",
                "charts/astronomer/templates/cli-install/cli-install-deployment.yaml",
                "charts/astronomer/templates/cli-install/cli-install-networkpolicy.yaml",
                "charts/astronomer/templates/cli-install/cli-install-service.yaml",
                "charts/astronomer/templates/cli-install/cli-install-ingress.yaml",
            ],
        )

        assert len(docs) == 5
        assert "install.example.com" in jmespath.search("spec.rules[*].host", docs[4])

    def test_astronomer_cli_install_disabled(self, kube_version):
        """Test that cli install service is disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"install": {"cliEnabled": False}}},
            show_only=[
                "charts/astronomer/templates/cli-install/cli-install-configmap.yaml",
                "charts/astronomer/templates/cli-install/cli-install-deployment.yaml",
                "charts/astronomer/templates/cli-install/cli-install-networkpolicy.yaml",
                "charts/astronomer/templates/cli-install/cli-install-service.yaml",
                "charts/astronomer/templates/cli-install/cli-install-ingress.yaml",
            ],
        )

        assert len(docs) == 0

    def test_astronomer_cli_install_ingress_disabled(self, kube_version):
        """Test that cli install service ingress is disabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={"astronomer": {"install": {"cliEnabled": False}}},
            show_only=[
                "charts/astronomer/templates/cli-install/cli-install-ingress.yaml"
            ],
        )

        assert len(docs) == 0
