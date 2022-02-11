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
        assert doc["metadata"]["name"] == "RELEASE-NAME-kube-state"

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
        assert doc["metadata"]["name"] == "RELEASE-NAME-kube-state"

        c_by_name = get_containers_by_name(doc)
        assert c_by_name["kube-state"]
        assert c_by_name["kube-state"]["resources"] == {
            "limits": {"cpu": "777m", "memory": "999Mi"},
            "requests": {"cpu": "666m", "memory": "888Mi"},
        }
