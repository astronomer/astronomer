from tests.chart_tests.helm_template_generator import render_chart
import pytest
from tests import supported_k8s_versions, get_containers_by_name


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
            "--metric-labels-allowlist=namespaces=[*],pods=[*]"
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

    def test_kube_state_default_collectors(self, kube_version):
        collector_resource_args = "--resources=daemonsets,leases,namespaces,nodes,configmaps,cronjobs,deployments,endpoints,horizontalpodautoscalers,ingresses,jobs,limitranges,networkpolicies,persistentvolumeclaims,poddisruptionbudgets,pods,replicasets,replicationcontrollers,resourcequotas,secrets,services,statefulsets"
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/kube-state/templates/kube-state-role.yaml",
                "charts/kube-state/templates/kube-state-deployment.yaml",
            ],
        )
        c_by_name = get_containers_by_name(docs[1])
        assert len(docs[0]["rules"]) == 23
        assert c_by_name["kube-state"]["args"][0] == collector_resource_args

    def test_kube_state_specific_collector_enabled(self, kube_version):
        collector_resource_args = "--resources=certificatesigningrequests"
        docs = render_chart(
            kube_version=kube_version,
            values={"kube-state": {"collectors": ["certificatesigningrequests"]}},
            show_only=[
                "charts/kube-state/templates/kube-state-role.yaml",
                "charts/kube-state/templates/kube-state-deployment.yaml",
            ],
        )
        c_by_name = get_containers_by_name(docs[1])
        assert len(docs[0]["rules"]) == 1
        assert c_by_name["kube-state"]["args"][0] == collector_resource_args

    def test_kube_state_disable_collectors(self, kube_version):
        collector_resource_args = "--resources="
        docs = render_chart(
            kube_version=kube_version,
            values={"kube-state": {"collectors": []}},
            show_only=[
                "charts/kube-state/templates/kube-state-role.yaml",
                "charts/kube-state/templates/kube-state-deployment.yaml",
            ],
        )
        c_by_name = get_containers_by_name(docs[1])
        assert c_by_name["kube-state"]["args"][0] == collector_resource_args
        assert docs[0]["rules"] is None

    def test_kube_state_metrics_priorityclass_defaults(self, kube_version):
        """Test to validate kube_state_metrics with priority class defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=["charts/kube-state/templates/kube-state-deployment.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert "priorityClassName" not in doc["spec"]["template"]["spec"]

    def test_kube_state_metrics_priorityclass_overrides(self, kube_version):
        """Test to validate kube_state_metrics with priority class configured."""
        docs = render_chart(
            kube_version=kube_version,
            values={"kube-state": {"priorityClassName": "kube-state-priority-pod"}},
            show_only=["charts/kube-state/templates/kube-state-deployment.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert "priorityClassName" in doc["spec"]["template"]["spec"]
        assert (
            "kube-state-priority-pod"
            == doc["spec"]["template"]["spec"]["priorityClassName"]
        )
