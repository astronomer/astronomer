import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


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
        assert "--metric-labels-allowlist=namespaces=[*],pods=[*],configmaps=[*]" in c_by_name["kube-state"]["args"]
        assert "--namespaces=" not in c_by_name["kube-state"]["args"]
        assert "--namespace=" not in c_by_name["kube-state"]["args"]

    def test_kube_state_deployment_namespace_pools(self, kube_version):
        """Test that global.features.namespacePools.enabled=true renders an accurate chart."""
        namespace_pools_list = ["test-1", "test-2", "test-3"]
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "features": {
                        "namespacePools": {
                            "enabled": True,
                            "namespaces": {"names": namespace_pools_list},
                        }
                    }
                }
            },
            namespace="test_namespace",
            show_only=[
                "charts/kube-state/templates/kube-state-deployment.yaml",
                "charts/kube-state/templates/kube-state-rolebinding.yaml",
                "charts/kube-state/templates/kube-state-role.yaml",
            ],
        )

        assert len(docs) == 9
        c_by_name = get_containers_by_name(docs[0])
        assert "--namespaces=test-1,test-2,test-3,test_namespace" in c_by_name["kube-state"]["args"]
        roles_namespace_pools_list = ["test-1", "test-2", "test-3", "test_namespace"]
        for i in range(1, 5):
            role_binding = docs[i]
            expected_subject = {
                "kind": "ServiceAccount",
                "name": "release-name-kube-state",
                "namespace": "test_namespace",
            }
            expected_role = {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": "release-name-kube-state",
            }
            assert role_binding["kind"] == "RoleBinding"
            assert role_binding["metadata"]["namespace"] == roles_namespace_pools_list[i - 5]
            assert role_binding["roleRef"] == expected_role
            assert role_binding["subjects"][0] == expected_subject

        for i in range(5, 9):
            role = docs[i]
            assert role["kind"] == "Role"
            assert role["metadata"]["namespace"] == roles_namespace_pools_list[i - 5]

    def test_kube_state_default_collectors(self, kube_version):
        collector_resource_args = "--resources=daemonsets,namespaces,configmaps,cronjobs,deployments,ingresses,jobs,limitranges,persistentvolumeclaims,pods,resourcequotas,secrets,services,statefulsets"
        docs = render_chart(
            kube_version=kube_version,
            values={},
            show_only=[
                "charts/kube-state/templates/kube-state-role.yaml",
                "charts/kube-state/templates/kube-state-deployment.yaml",
            ],
        )
        c_by_name = get_containers_by_name(docs[1])
        assert len(docs[0]["rules"]) == 14
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
        assert "certificatesigningrequests" in docs[0]["rules"][0]["resources"]
        assert docs[0]["rules"] == [
            {
                "apiGroups": ["certificates.k8s.io"],
                "resources": ["certificatesigningrequests"],
                "verbs": ["list", "watch"],
            }
        ]
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
        assert "kube-state-priority-pod" == doc["spec"]["template"]["spec"]["priorityClassName"]
