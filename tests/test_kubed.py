from tests.helm_template_generator import render_chart
from subprocess import CalledProcessError
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestKubed:
    show_only = [
        "charts/kubed/templates/kubed-apiregistration.yaml",
        "charts/kubed/templates/kubed-clusterrole.yaml",
        "charts/kubed/templates/kubed-clusterrolebinding.yaml",
        "charts/kubed/templates/kubed-deployment.yaml",
        "charts/kubed/templates/kubed-notifier-secert.yaml",
        "charts/kubed/templates/kubed-pvc.yaml",
        "charts/kubed/templates/kubed-secret.yaml",
        "charts/kubed/templates/kubed-service.yaml",
        "charts/kubed/templates/kubed-serviceaccount.yaml",
        "charts/kubed/templates/kubed-user-roles.yaml",
    ]

    def test_kubed_defaults(self, kube_version):
        """Test that helm renders a good chart for kubed with defaults."""
        docs = render_chart(
            kube_version=kube_version,
            show_only=self.show_only,
        )

        assert len(docs) == 11

    def test_kubed_disabled(self, kube_version):
        """Test that helm renders does not render any k8s manifests when kubed is disabled."""
        with pytest.raises(CalledProcessError):
            render_chart(
                kube_version=kube_version,
                values={"global": {"kubedEnabled": False}},
                show_only=self.show_only,
            )
