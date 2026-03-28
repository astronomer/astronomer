import subprocess

import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart

# external-secrets is a data-plane-only component
ESO_VALUES = {"external-secrets": {"enabled": True}}
ESO_DATA_PLANE_VALUES = {**ESO_VALUES, "global": {"plane": {"mode": "data"}}}

DEPLOYMENT_TEMPLATE = "charts/external-secrets/templates/deployment.yaml"
WEBHOOK_DEPLOYMENT_TEMPLATE = "charts/external-secrets/templates/webhook-deployment.yaml"
WEBHOOK_SERVICE_TEMPLATE = "charts/external-secrets/templates/webhook-service.yaml"
SERVICEACCOUNT_TEMPLATE = "charts/external-secrets/templates/serviceaccount.yaml"
WEBHOOK_SERVICEACCOUNT_TEMPLATE = "charts/external-secrets/templates/webhook-serviceaccount.yaml"
RBAC_TEMPLATE = "charts/external-secrets/templates/rbac.yaml"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestExternalSecretsDeployment:
    def test_deployment_defaults(self, kube_version):
        """Test that the external-secrets operator deployment renders correctly with defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[DEPLOYMENT_TEMPLATE],
        )
        assert len(docs) == 1
        doc = docs[0]

        assert doc["apiVersion"] == "apps/v1"
        assert doc["kind"] == "Deployment"
        assert doc["metadata"]["name"] == "release-name-external-secrets"
        assert doc["spec"]["replicas"] == 1
        assert doc["spec"]["template"]["metadata"]["labels"]["tier"] == "dp-failover"
        assert doc["spec"]["template"]["metadata"]["labels"]["component"] == "external-secrets"
        assert doc["spec"]["template"]["metadata"]["labels"]["release"] == "release-name"

    def test_deployment_image(self, kube_version):
        """Test that the operator deployment uses the correct image."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[DEPLOYMENT_TEMPLATE],
        )
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        assert "external-secrets" in c_by_name
        container = c_by_name["external-secrets"]
        assert container["image"] == "quay.io/astronomer/ap-external-secrets:2.2.0"
        assert container["imagePullPolicy"] == "IfNotPresent"

    def test_deployment_private_registry(self, kube_version):
        """Test that the operator deployment respects global.privateRegistry."""
        private_repo = "registry.example.com/myorg"
        docs = render_chart(
            kube_version=kube_version,
            values={
                **ESO_VALUES,
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        "repository": private_repo,
                    }
                },
            },
            show_only=[DEPLOYMENT_TEMPLATE],
        )
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        assert c_by_name["external-secrets"]["image"].startswith(private_repo)

    def test_deployment_resources(self, kube_version):
        """Test that the operator deployment has resource requests and limits set."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[DEPLOYMENT_TEMPLATE],
        )
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        resources = c_by_name["external-secrets"]["resources"]
        assert "cpu" in resources["requests"]
        assert "memory" in resources["requests"]
        assert "cpu" in resources["limits"]
        assert "memory" in resources["limits"]

    def test_deployment_security_context(self, kube_version):
        """Test that the operator container has readOnlyRootFilesystem set."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[DEPLOYMENT_TEMPLATE],
        )
        doc = docs[0]
        c_by_name = get_containers_by_name(doc)
        sc = c_by_name["external-secrets"]["securityContext"]
        assert sc["readOnlyRootFilesystem"] is True
        assert sc["allowPrivilegeEscalation"] is False
        assert sc["runAsNonRoot"] is True

    def test_deployment_node_pool(self, kube_version):
        """Test that the operator deployment includes nodeSelector, affinity, and tolerations."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[DEPLOYMENT_TEMPLATE],
        )
        spec = docs[0]["spec"]["template"]["spec"]
        assert "nodeSelector" in spec
        assert "affinity" in spec
        assert "tolerations" in spec

    def test_deployment_replica_override(self, kube_version):
        """Test that replicaCount can be overridden."""
        docs = render_chart(
            kube_version=kube_version,
            values={**ESO_VALUES, "external-secrets": {"enabled": True, "replicaCount": 3}},
            show_only=[DEPLOYMENT_TEMPLATE],
        )
        assert docs[0]["spec"]["replicas"] == 3

    def test_deployment_disabled_by_default(self, kube_version):
        """Test that external-secrets deployment is not rendered when the subchart is disabled.

        Helm errors with 'could not find template' when --show-only targets a
        template that renders to empty output, which is the expected behaviour
        when the subchart is disabled.
        """
        with pytest.raises(subprocess.CalledProcessError):
            render_chart(
                kube_version=kube_version,
                values={},
                show_only=[DEPLOYMENT_TEMPLATE],
            )


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestExternalSecretsWebhookDeployment:
    def test_webhook_deployment_defaults(self, kube_version):
        """Test that the webhook deployment renders correctly with defaults."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[WEBHOOK_DEPLOYMENT_TEMPLATE],
        )
        assert len(docs) == 1
        doc = docs[0]

        assert doc["apiVersion"] == "apps/v1"
        assert doc["kind"] == "Deployment"
        assert doc["metadata"]["name"] == "release-name-external-secrets-webhook"
        assert doc["spec"]["replicas"] == 1
        assert doc["spec"]["template"]["metadata"]["labels"]["tier"] == "dp-failover"
        assert doc["spec"]["template"]["metadata"]["labels"]["release"] == "release-name"

    def test_webhook_deployment_image(self, kube_version):
        """Test that the webhook deployment uses the correct image."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[WEBHOOK_DEPLOYMENT_TEMPLATE],
        )
        c_by_name = get_containers_by_name(docs[0])
        assert "webhook" in c_by_name
        assert c_by_name["webhook"]["image"] == "quay.io/astronomer/ap-external-secrets:2.2.0"
        assert c_by_name["webhook"]["imagePullPolicy"] == "IfNotPresent"

    def test_webhook_deployment_private_registry(self, kube_version):
        """Test that the webhook deployment respects global.privateRegistry."""
        private_repo = "registry.example.com/myorg"
        docs = render_chart(
            kube_version=kube_version,
            values={
                **ESO_VALUES,
                "global": {
                    "privateRegistry": {
                        "enabled": True,
                        "repository": private_repo,
                    }
                },
            },
            show_only=[WEBHOOK_DEPLOYMENT_TEMPLATE],
        )
        c_by_name = get_containers_by_name(docs[0])
        assert c_by_name["webhook"]["image"].startswith(private_repo)

    def test_webhook_deployment_resources(self, kube_version):
        """Test that the webhook deployment has resource requests and limits set."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[WEBHOOK_DEPLOYMENT_TEMPLATE],
        )
        c_by_name = get_containers_by_name(docs[0])
        resources = c_by_name["webhook"]["resources"]
        assert "cpu" in resources["requests"]
        assert "memory" in resources["requests"]
        assert "cpu" in resources["limits"]
        assert "memory" in resources["limits"]

    def test_webhook_deployment_security_context(self, kube_version):
        """Test that the webhook container has readOnlyRootFilesystem set."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[WEBHOOK_DEPLOYMENT_TEMPLATE],
        )
        c_by_name = get_containers_by_name(docs[0])
        sc = c_by_name["webhook"]["securityContext"]
        assert sc["readOnlyRootFilesystem"] is True
        assert sc["allowPrivilegeEscalation"] is False
        assert sc["runAsNonRoot"] is True

    def test_webhook_deployment_node_pool(self, kube_version):
        """Test that the webhook deployment includes nodeSelector, affinity, and tolerations."""
        spec = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[WEBHOOK_DEPLOYMENT_TEMPLATE],
        )[0]["spec"]["template"]["spec"]
        assert "nodeSelector" in spec
        assert "affinity" in spec
        assert "tolerations" in spec

    def test_webhook_disabled(self, kube_version):
        """Test that the webhook deployment is not rendered when webhook.create is false."""
        with pytest.raises(subprocess.CalledProcessError):
            render_chart(
                kube_version=kube_version,
                values={**ESO_VALUES, "external-secrets": {"enabled": True, "webhook": {"create": False}}},
                show_only=[WEBHOOK_DEPLOYMENT_TEMPLATE],
            )


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestExternalSecretsWebhookService:
    def test_webhook_service_defaults(self, kube_version):
        """Test that the webhook service renders correctly."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[WEBHOOK_SERVICE_TEMPLATE],
        )
        assert len(docs) == 1
        doc = docs[0]

        assert doc["apiVersion"] == "v1"
        assert doc["kind"] == "Service"
        assert doc["metadata"]["name"] == "release-name-external-secrets-webhook"

        ports = {p["name"]: p for p in doc["spec"]["ports"]}
        assert "webhook" in ports
        assert ports["webhook"]["port"] == 443
        assert ports["webhook"]["protocol"] == "TCP"
        assert ports["webhook"]["appProtocol"] == "https"

    def test_webhook_service_selector(self, kube_version):
        """Test that the webhook service selector matches the webhook deployment."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[WEBHOOK_SERVICE_TEMPLATE],
        )
        selector = docs[0]["spec"]["selector"]
        assert "app.kubernetes.io/name" in selector
        assert selector["app.kubernetes.io/name"] == "external-secrets-webhook"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestExternalSecretsServiceAccounts:
    def test_serviceaccount_created_by_default(self, kube_version):
        """Test that the operator ServiceAccount is created by default."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[SERVICEACCOUNT_TEMPLATE],
        )
        sa_docs = [d for d in docs if d["kind"] == "ServiceAccount"]
        assert len(sa_docs) == 1
        assert sa_docs[0]["metadata"]["name"] == "release-name-external-secrets"

    def test_webhook_serviceaccount_created_by_default(self, kube_version):
        """Test that the webhook ServiceAccount is created by default."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[WEBHOOK_SERVICEACCOUNT_TEMPLATE],
        )
        sa_docs = [d for d in docs if d["kind"] == "ServiceAccount"]
        assert len(sa_docs) == 1
        assert sa_docs[0]["metadata"]["name"] == "release-name-external-secrets-webhook"

    def test_serviceaccount_create_disabled(self, kube_version):
        """Test that no SA is rendered when create is false."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                **ESO_VALUES,
                "external-secrets": {
                    "enabled": True,
                    "serviceAccount": {"create": False},
                    "webhook": {"serviceAccount": {"create": False}},
                },
            },
            show_only=[SERVICEACCOUNT_TEMPLATE, WEBHOOK_SERVICEACCOUNT_TEMPLATE],
        )
        assert len([d for d in docs if d["kind"] == "ServiceAccount"]) == 0

    def test_serviceaccount_custom_name(self, kube_version):
        """Test that a custom SA name is used when specified."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                **ESO_VALUES,
                "external-secrets": {
                    "enabled": True,
                    "serviceAccount": {"create": True, "name": "my-custom-sa"},
                },
            },
            show_only=[SERVICEACCOUNT_TEMPLATE],
        )
        sa_docs = [d for d in docs if d["kind"] == "ServiceAccount"]
        assert sa_docs[0]["metadata"]["name"] == "my-custom-sa"

    def test_serviceaccount_annotations(self, kube_version):
        """Test that custom annotations are applied to the ServiceAccount."""
        annotations = {"eks.amazonaws.com/role-arn": "arn:aws:iam::123456789:role/my-role"}
        docs = render_chart(
            kube_version=kube_version,
            values={
                **ESO_VALUES,
                "external-secrets": {
                    "enabled": True,
                    "serviceAccount": {"create": True, "annotations": annotations},
                },
            },
            show_only=[SERVICEACCOUNT_TEMPLATE],
        )
        sa_docs = [d for d in docs if d["kind"] == "ServiceAccount"]
        assert sa_docs[0]["metadata"]["annotations"] == annotations


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestExternalSecretsRBAC:
    def test_rbac_created_by_default(self, kube_version):
        """Test that RBAC resources are created by default."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_VALUES,
            show_only=[RBAC_TEMPLATE],
        )
        kinds = {d["kind"] for d in docs}
        assert "ClusterRole" in kinds
        assert "ClusterRoleBinding" in kinds

    def test_rbac_disabled(self, kube_version):
        """Test that no RBAC resources are rendered when rbac.create is false."""
        with pytest.raises(subprocess.CalledProcessError):
            render_chart(
                kube_version=kube_version,
                values={**ESO_VALUES, "external-secrets": {"enabled": True, "rbac": {"create": False}}},
                show_only=[RBAC_TEMPLATE],
            )


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestExternalSecretsCRDs:
    def test_crds_installed_by_default(self, kube_version):
        """Test that CRDs are rendered by default when installCRDs is true."""
        crd_templates = [
            "charts/external-secrets/templates/crd-clustersecretstores.external-secrets.io.yaml",
            "charts/external-secrets/templates/crd-externalsecrets.external-secrets.io.yaml",
            "charts/external-secrets/templates/crd-pushsecrets.external-secrets.io.yaml",
        ]
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values=ESO_VALUES,
            show_only=crd_templates,
        )
        assert len(docs) > 0
        for doc in docs:
            assert doc["kind"] == "CustomResourceDefinition"
            assert doc["apiVersion"] == "apiextensions.k8s.io/v1"

    def test_crds_not_rendered_when_subchart_disabled(self, kube_version):
        """Test that CRDs are not rendered when the subchart is disabled (the default)."""
        crd_templates = [
            "charts/external-secrets/templates/crd-clustersecretstores.external-secrets.io.yaml",
            "charts/external-secrets/templates/crd-externalsecrets.external-secrets.io.yaml",
            "charts/external-secrets/templates/crd-pushsecrets.external-secrets.io.yaml",
        ]
        # When the subchart is disabled, helm errors on --show-only because no
        # output is produced for any of the CRD templates.
        with pytest.raises(subprocess.CalledProcessError):
            render_chart(
                kube_version=kube_version,
                validate_objects=False,
                values={},
                show_only=crd_templates,
            )


@pytest.mark.parametrize("plane_mode", ["unified", "control", "data"])
def test_external_secrets_only_renders_when_enabled(plane_mode):
    """Test that external-secrets templates only render when explicitly enabled, regardless of plane mode."""

    # When the subchart is disabled, helm errors with 'could not find template'
    # because --show-only targets a template that produces no output.
    with pytest.raises(subprocess.CalledProcessError):
        render_chart(
            values={"global": {"plane": {"mode": plane_mode}}},
            show_only=[DEPLOYMENT_TEMPLATE, WEBHOOK_DEPLOYMENT_TEMPLATE],
        )

    docs_enabled = render_chart(
        values={**ESO_VALUES, "global": {"plane": {"mode": plane_mode}}},
        show_only=[DEPLOYMENT_TEMPLATE, WEBHOOK_DEPLOYMENT_TEMPLATE],
    )
    assert len(docs_enabled) == 2, (
        f"Expected 2 external-secrets deployments when enabled in plane.mode={plane_mode}, got {len(docs_enabled)}"
    )


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestExternalSecretsDataPlaneMode:
    def test_tier_label_is_dp_failover(self, kube_version):
        """Test that both deployments carry the dp-failover tier label."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_DATA_PLANE_VALUES,
            show_only=[DEPLOYMENT_TEMPLATE, WEBHOOK_DEPLOYMENT_TEMPLATE],
        )
        assert len(docs) == 2
        for doc in docs:
            pod_labels = doc["spec"]["template"]["metadata"]["labels"]
            assert pod_labels["tier"] == "dp-failover"

    def test_global_pod_labels_applied(self, kube_version):
        """Test that global.podLabels are propagated to external-secrets pods."""
        custom_labels = {"foo": "FOO", "bar": "BAR"}
        docs = render_chart(
            kube_version=kube_version,
            values={**ESO_DATA_PLANE_VALUES, "global": {"plane": {"mode": "data"}, "podLabels": custom_labels}},
            show_only=[DEPLOYMENT_TEMPLATE, WEBHOOK_DEPLOYMENT_TEMPLATE],
        )
        for doc in docs:
            pod_labels = doc["spec"]["template"]["metadata"]["labels"]
            for key, value in custom_labels.items():
                assert pod_labels.get(key) == value, f"Label {key}={value} missing from {doc['metadata']['name']}"
