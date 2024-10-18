from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import get_containers_by_name, supported_k8s_versions
import jmespath


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerCliInstall:
    def test_astronomer_cli_install_default(self, kube_version):
        """Test that helm renders a good deployment template for astronomer/cli-install using default values."""
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

        c_by_name = get_containers_by_name(docs[1])

        assert c_by_name["cli-install"]["livenessProbe"]["initialDelaySeconds"] == 10
        assert c_by_name["cli-install"]["livenessProbe"]["periodSeconds"] == 15
        assert c_by_name["cli-install"]["livenessProbe"]["timeoutSeconds"] == 1
        assert c_by_name["cli-install"]["livenessProbe"]["failureThreshold"] == 5
        assert c_by_name["cli-install"]["readinessProbe"]["initialDelaySeconds"] == 10
        assert c_by_name["cli-install"]["readinessProbe"]["periodSeconds"] == 15
        assert c_by_name["cli-install"]["readinessProbe"]["timeoutSeconds"] == 1
        assert c_by_name["cli-install"]["readinessProbe"]["failureThreshold"] == 5

    def test_astronomer_cli_install_custom_values(self, kube_version):
        """Test that helm renders a good deployment template for astronomer/cli-install using custom values."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=[
                "charts/astronomer/templates/cli-install/cli-install-configmap.yaml",
                "charts/astronomer/templates/cli-install/cli-install-deployment.yaml",
                "charts/astronomer/templates/cli-install/cli-install-networkpolicy.yaml",
                "charts/astronomer/templates/cli-install/cli-install-service.yaml",
                "charts/astronomer/templates/cli-install/cli-install-ingress.yaml",
            ],
            values={
                "astronomer": {
                    "install": {
                        "livenessProbe": {
                            "initialDelaySeconds": 999,
                            "periodSeconds": 998,
                            "timeoutSeconds": 997,
                            "failureThreshold": 996,
                        },
                        "readinessProbe": {
                            "initialDelaySeconds": 995,
                            "periodSeconds": 994,
                            "timeoutSeconds": 993,
                            "failureThreshold": 992,
                        },
                    }
                },
            },
        )

        assert len(docs) == 5
        assert "install.example.com" in jmespath.search("spec.rules[*].host", docs[4])

        c_by_name = get_containers_by_name(docs[1])

        assert c_by_name["cli-install"]["livenessProbe"]["initialDelaySeconds"] == 999
        assert c_by_name["cli-install"]["livenessProbe"]["periodSeconds"] == 998
        assert c_by_name["cli-install"]["livenessProbe"]["timeoutSeconds"] == 997
        assert c_by_name["cli-install"]["livenessProbe"]["failureThreshold"] == 996
        assert c_by_name["cli-install"]["readinessProbe"]["initialDelaySeconds"] == 995
        assert c_by_name["cli-install"]["readinessProbe"]["periodSeconds"] == 994
        assert c_by_name["cli-install"]["readinessProbe"]["timeoutSeconds"] == 993
        assert c_by_name["cli-install"]["readinessProbe"]["failureThreshold"] == 992

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
            show_only=["charts/astronomer/templates/cli-install/cli-install-ingress.yaml"],
        )

        assert len(docs) == 0
