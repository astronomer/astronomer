from tests.helm_template_generator import render_chart
import jmespath
import pytest
from . import supported_k8s_versions


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestResourceLimits:
    def test_default_kube_state_deployment_resources(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/kube-state/templates/kube-state-deployment.yaml"],
        )

        assert "Deployment" == jmespath.search("kind", docs[0])
        assert "RELEASE-NAME-kube-state" == jmespath.search("metadata.name", docs[0])
        assert "kube-state" == jmespath.search(
            "spec.template.spec.containers[0].name", docs[0]
        )
        assert jmespath.search(
            "spec.template.spec.containers[0].resources", docs[0]
        ) == {
            "limits": {"cpu": "100m", "memory": "128Mi"},
            "requests": {"cpu": "100m", "memory": "128Mi"},
        }

    def test_override_default_kube_state_deployment_resources(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "kube-state": {
                    "resources": {
                        "limits": {"cpu": "200m", "memory": "256Mi"},
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                    }
                },
            },
            show_only=["charts/kube-state/templates/kube-state-deployment.yaml"],
        )

        assert "Deployment" == jmespath.search("kind", docs[0])
        assert "RELEASE-NAME-kube-state" == jmespath.search("metadata.name", docs[0])
        assert "kube-state" == jmespath.search(
            "spec.template.spec.containers[0].name", docs[0]
        )
        assert "256Mi" == jmespath.search(
            "spec.template.spec.containers[0].resources.limits.memory", docs[0]
        )
        assert "128Mi" == jmespath.search(
            "spec.template.spec.containers[0].resources.requests.memory", docs[0]
        )
        assert "100m" == jmespath.search(
            "spec.template.spec.containers[0].resources.requests.cpu", docs[0]
        )
        assert "200m" == jmespath.search(
            "spec.template.spec.containers[0].resources.limits.cpu", docs[0]
        )

    def test_default_prometheus_nodexporter_daemonset_resources(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/prometheus-node-exporter/templates/daemonset.yaml"],
        )

        assert "DaemonSet" == jmespath.search("kind", docs[0])
        assert "RELEASE-NAME-prometheus-node-exporter" == jmespath.search(
            "metadata.name", docs[0]
        )
        assert "node-exporter" == jmespath.search(
            "spec.template.spec.containers[0].name", docs[0]
        )
        assert jmespath.search(
            "spec.template.spec.containers[0].resources", docs[0]
        ) == {
            "limits": {"cpu": "100m", "memory": "128Mi"},
            "requests": {"cpu": "10m", "memory": "128Mi"},
        }
