from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions, get_containers_by_name


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestKubeStateDeployment:
    def test_kube_state_deployment_default_resources(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/kube-state/templates/kube-state-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "Deployment"
        assert doc["metadata"]["name"] == "release-name-kube-state"

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["kube-state"]
        assert c_by_name["kube-state"]["resources"] == {
            "limits": {"cpu": "500m", "memory": "1024Mi"},
            "requests": {"cpu": "250m", "memory": "512Mi"},
        }

    def test_kube_state_deployment_custom_resources(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "kube-state": {
                    "resources": {
                        "limits": {"cpu": "777m", "memory": "999Mi"},
                        "requests": {"cpu": "666m", "memory": "888Mi"},
                    }
                },
            },
            show_only=["charts/kube-state/templates/kube-state-deployment.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["kind"] == "Deployment"
        assert doc["metadata"]["name"] == "release-name-kube-state"

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["kube-state"]
        assert c_by_name["kube-state"]["resources"] == {
            "limits": {"cpu": "777m", "memory": "999Mi"},
            "requests": {"cpu": "666m", "memory": "888Mi"},
        }

    def test_kube_state_deployment_with_default_args(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "kube-state": {},
            },
            show_only=["charts/kube-state/templates/kube-state-deployment.yaml"],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert (
            "--metric-labels-allowlist=namespaces=[*]"
            in c_by_name["kube-state"]["args"]
        )
        assert "--namespaces=" not in c_by_name["kube-state"]["args"]
        assert "--namespace=" not in c_by_name["kube-state"]["args"]

    def test_kube_state_deployment_singleNamespace(self, kube_version):
        """Test that global.singleNamespace=asdf renders an accurate chart."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"singleNamespace": True}},
            namespace="test_namespace",
            show_only=["charts/kube-state/templates/kube-state-deployment.yaml"],
        )
        c_by_name = get_containers_by_name(docs[0])
        assert "--namespaces=test_namespace" in c_by_name["kube-state"]["args"]
