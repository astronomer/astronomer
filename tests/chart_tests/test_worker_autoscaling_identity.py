"""The identity KEDA presents to the platform's worker-scaling endpoint.

KEDA authenticates a scaling request with a short-lived token minted for the service account
named on the ClusterTriggerAuthentication the ScaledObject references. The chart creates that
account, and the Role/RoleBinding that lets the customer's keda-operator mint a token for it,
inside the namespace KEDA resolves cluster-scoped objects in.

Two constraints are easy to break and are asserted below. A ClusterTriggerAuthentication is
cluster-scoped, so it must render with no namespace; and a stock KEDA install grants itself no
`serviceaccounts/token: create` anywhere, so without the binding the mint fails silently and the
trigger sends an empty token.
"""

import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart

IDENTITY = "metrics-api-worker-trigger"
TOKEN_MINTER = f"{IDENTITY}-token-minter"

show_only = [
    "templates/worker-autoscaling/serviceaccount.yaml",
    "templates/worker-autoscaling/rbac.yaml",
    "templates/worker-autoscaling/clustertriggerauthentication.yaml",
]

OBJECT_NAMES = {IDENTITY, TOKEN_MINTER}


def keda_values(plane_mode="unified", **keda):
    return {"global": {"plane": {"mode": plane_mode}, "keda": {"enabled": True, **keda}}}


def by_kind(docs):
    return {doc["kind"]: doc for doc in docs}


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestWorkerAutoscalingIdentity:
    def test_nothing_rendered_by_default(self, kube_version):
        """Test that a platform install with worker autoscaling off creates none of the objects."""
        docs = render_chart(kube_version=kube_version)

        assert not [doc for doc in docs if (doc.get("metadata") or {}).get("name") in OBJECT_NAMES]

    @pytest.mark.parametrize("plane_mode", ["data", "unified"])
    def test_rendered_when_enabled(self, kube_version, plane_mode):
        """Test that turning worker autoscaling on creates the identity, its binding and the auth object."""
        docs = render_chart(kube_version=kube_version, show_only=show_only, values=keda_values(plane_mode))

        assert len(docs) == 4
        docs_by_kind = by_kind(docs)
        assert set(docs_by_kind) == {"ServiceAccount", "Role", "RoleBinding", "ClusterTriggerAuthentication"}

        assert docs_by_kind["ServiceAccount"]["metadata"]["name"] == IDENTITY
        assert docs_by_kind["Role"]["metadata"]["name"] == TOKEN_MINTER
        assert docs_by_kind["RoleBinding"]["metadata"]["name"] == TOKEN_MINTER
        assert docs_by_kind["ClusterTriggerAuthentication"]["metadata"]["name"] == IDENTITY

        for kind in ("ServiceAccount", "Role", "RoleBinding"):
            assert docs_by_kind[kind]["metadata"]["namespace"] == "keda"

        # The astronomer.io label is what tells whoever reads the KEDA namespace who put these there.
        for doc in docs:
            labels = doc["metadata"]["labels"]
            assert labels["tier"] == "astronomer"
            assert labels["component"] == "worker-autoscaling"
            assert labels["release"] == "release-name"
            assert labels["heritage"] == "Helm"
            assert labels["astronomer.io/platform-release"] == "release-name"
            assert labels["chart"].startswith("astronomer-")

    def test_not_rendered_on_a_control_plane(self, kube_version):
        """Test that a control plane creates nothing: KEDA scales workers, which only run on a data plane."""
        docs = render_chart(kube_version=kube_version, values=keda_values("control"))

        assert not [doc for doc in docs if (doc.get("metadata") or {}).get("name") in OBJECT_NAMES]

    def test_service_account_is_not_mounted(self, kube_version):
        """Test that the identity is not mounted anywhere, so a token can only come from a deliberate mint."""
        docs = render_chart(
            kube_version=kube_version,
            show_only="templates/worker-autoscaling/serviceaccount.yaml",
            values=keda_values(),
        )

        assert docs[0]["automountServiceAccountToken"] is False

    def test_cluster_trigger_authentication_is_cluster_scoped(self, kube_version):
        """Test that the auth object renders without a namespace and names the dedicated identity."""
        docs = render_chart(
            kube_version=kube_version,
            show_only="templates/worker-autoscaling/clustertriggerauthentication.yaml",
            values=keda_values(),
        )

        assert docs[0]["apiVersion"] == "keda.sh/v1alpha1"
        assert "namespace" not in docs[0]["metadata"]
        assert docs[0]["spec"]["boundServiceAccountToken"] == [{"parameter": "token", "serviceAccountName": IDENTITY}]

    def test_token_minter_is_scoped_to_the_one_identity(self, kube_version):
        """Test that KEDA can mint a token for the scaling identity and for no other account."""
        docs = render_chart(kube_version=kube_version, show_only="templates/worker-autoscaling/rbac.yaml", values=keda_values())
        docs_by_kind = by_kind(docs)
        role, role_binding = docs_by_kind["Role"], docs_by_kind["RoleBinding"]

        assert role["rules"] == [
            {
                "apiGroups": [""],
                "resources": ["serviceaccounts/token"],
                "resourceNames": [IDENTITY],
                "verbs": ["create"],
            }
        ]
        assert role_binding["roleRef"] == {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": TOKEN_MINTER}
        assert role_binding["subjects"] == [{"kind": "ServiceAccount", "name": "keda-operator", "namespace": "keda"}]

    def test_identity_holds_no_permissions_of_its_own(self, kube_version):
        """Test that nothing binds a role to the identity, so a leaked token grants only the queue depths."""
        docs = render_chart(kube_version=kube_version, values=keda_values())

        subjects = [
            subject for doc in docs if doc["kind"] in ("RoleBinding", "ClusterRoleBinding") for subject in doc.get("subjects") or []
        ]
        assert not [subject for subject in subjects if subject.get("name") == IDENTITY]

    def test_objects_follow_the_cluster_object_namespace(self, kube_version):
        """Test that the objects land where KEDA resolves cluster-scoped objects, not where KEDA runs.

        KEDA reads KEDA_CLUSTER_OBJECT_NAMESPACE for that, falling back to the operator pod's own
        namespace. The binding's subject stays in the namespace KEDA actually runs in, which makes
        it a cross-namespace subject whenever the two differ.
        """
        docs = render_chart(
            kube_version=kube_version,
            show_only=show_only,
            values=keda_values(
                plane_mode="data",
                namespace="keda-system",
                clusterObjectNamespace="keda-cluster",
                operatorServiceAccountName="keda-operator-sa",
            ),
        )
        docs_by_kind = by_kind(docs)

        for kind in ("ServiceAccount", "Role", "RoleBinding"):
            assert docs_by_kind[kind]["metadata"]["namespace"] == "keda-cluster"
        assert docs_by_kind["RoleBinding"]["subjects"] == [
            {"kind": "ServiceAccount", "name": "keda-operator-sa", "namespace": "keda-system"}
        ]

    def test_rendered_regardless_of_the_kubernetes_rbac_flag(self, kube_version):
        """Test that global.rbac.enabled does not suppress half of the bundle.

        Rendering the identity without its binding is the silently-broken install this feature has
        to avoid: KEDA would present an account it cannot obtain a token for. Turning worker
        autoscaling on is the opt-in to all four objects.
        """
        values = keda_values()
        values["global"]["rbac"] = {"enabled": False}
        docs = render_chart(kube_version=kube_version, show_only=show_only, values=values)

        assert len(docs) == 4

    def test_keda_namespace_is_required(self, kube_version):
        """Test that the install fails fast rather than writing the objects where KEDA never looks."""
        with pytest.raises(Exception) as err:
            render_chart(kube_version=kube_version, values=keda_values(namespace=""))

        assert "global.keda.namespace is required" in err.value.stderr.decode()
