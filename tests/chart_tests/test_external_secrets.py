import base64
import subprocess

import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart

# external-secrets is a data-plane-only component; all templates require plane.mode=="data"
ESO_VALUES = {"external-secrets": {"enabled": True}, "global": {"plane": {"mode": "data"}}}
ESO_DATA_PLANE_VALUES = ESO_VALUES  # alias kept for readability

DEPLOYMENT_TEMPLATE = "charts/external-secrets/templates/deployment.yaml"
SERVICEACCOUNT_TEMPLATE = "charts/external-secrets/templates/serviceaccount.yaml"
RBAC_TEMPLATE = "charts/external-secrets/templates/rbac.yaml"
CLUSTER_SECRET_STORE_TEMPLATE = "charts/external-secrets/templates/cluster-secret-store.yaml"
SECRETS_BACKEND_CREDENTIALS_TEMPLATE = "charts/external-secrets/templates/secrets-backend-credentials.yaml"


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
                    "plane": {"mode": "data"},
                    "privateRegistry": {
                        "enabled": True,
                        "repository": private_repo,
                    },
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
            values={
                **ESO_VALUES,
                "external-secrets": {"enabled": True, "replicaCount": 3},
            },
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

    def test_serviceaccount_create_disabled(self, kube_version):
        """Test that no SA is rendered when create is false."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                **ESO_VALUES,
                "external-secrets": {
                    "enabled": True,
                    "serviceAccount": {"create": False},
                },
            },
            show_only=[SERVICEACCOUNT_TEMPLATE],
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
        """Test that no RBAC resources are rendered when rbac.create is false.

        The template has a static comment header outside the if-block so helm
        does not error — it returns an empty document list instead.
        """
        docs = render_chart(
            kube_version=kube_version,
            values={
                **ESO_VALUES,
                "external-secrets": {"enabled": True, "rbac": {"create": False}},
            },
            show_only=[RBAC_TEMPLATE],
        )
        assert len(docs) == 0


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
    """Test that external-secrets deployment only renders in data plane mode when enabled.

    When the subchart is entirely absent (not enabled at umbrella level), helm
    cannot find any of its templates and raises an error.  When the subchart IS
    enabled, the deployment only renders if plane.mode == 'data'.
    """
    # When the subchart is entirely disabled helm errors regardless of plane mode.
    with pytest.raises(subprocess.CalledProcessError):
        render_chart(
            values={"global": {"plane": {"mode": plane_mode}}},
            show_only=[DEPLOYMENT_TEMPLATE],
        )

    # When the subchart is enabled, deployment renders only in data plane mode.
    docs = render_chart(
        values={
            "external-secrets": {"enabled": True},
            "global": {"plane": {"mode": plane_mode}},
        },
        show_only=[DEPLOYMENT_TEMPLATE],
    )
    if plane_mode == "data":
        assert len(docs) == 1, f"Expected 1 external-secrets deployment in plane.mode=data, got {len(docs)}"
    else:
        assert len(docs) == 0, f"Expected 0 external-secrets deployments in plane.mode={plane_mode}, got {len(docs)}"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestExternalSecretsDataPlaneMode:
    def test_tier_label_is_dp_failover(self, kube_version):
        """Test that the operator deployment carries the dp-failover tier label."""
        docs = render_chart(
            kube_version=kube_version,
            values=ESO_DATA_PLANE_VALUES,
            show_only=[DEPLOYMENT_TEMPLATE],
        )
        assert len(docs) == 1
        for doc in docs:
            pod_labels = doc["spec"]["template"]["metadata"]["labels"]
            assert pod_labels["tier"] == "dp-failover"

    def test_global_pod_labels_applied(self, kube_version):
        """Test that global.podLabels are propagated to external-secrets pods."""
        custom_labels = {"foo": "FOO", "bar": "BAR"}
        docs = render_chart(
            kube_version=kube_version,
            values={
                **ESO_DATA_PLANE_VALUES,
                "global": {"plane": {"mode": "data"}, "podLabels": custom_labels},
            },
            show_only=[DEPLOYMENT_TEMPLATE],
        )
        for doc in docs:
            pod_labels = doc["spec"]["template"]["metadata"]["labels"]
            for key, value in custom_labels.items():
                assert pod_labels.get(key) == value, f"Label {key}={value} missing from {doc['metadata']['name']}"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestClusterSecretStore:
    def test_renders_in_data_plane_mode(self, kube_version):
        """ClusterSecretStore renders when plane.mode is 'data'."""
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values=ESO_VALUES,
            show_only=[CLUSTER_SECRET_STORE_TEMPLATE],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["apiVersion"] == "external-secrets.io/v1"
        assert doc["kind"] == "ClusterSecretStore"

    def test_not_rendered_outside_data_plane(self, kube_version):
        """ClusterSecretStore is not rendered when plane.mode is not 'data'."""
        for mode in ("control", "unified"):
            docs = render_chart(
                kube_version=kube_version,
                validate_objects=False,
                values={
                    "external-secrets": {"enabled": True},
                    "global": {"plane": {"mode": mode}},
                },
                show_only=[CLUSTER_SECRET_STORE_TEMPLATE],
            )
            assert len(docs) == 0, f"Expected no ClusterSecretStore in plane.mode={mode}"

    def test_default_name_and_region(self, kube_version):
        """ClusterSecretStore uses default name and region from values."""
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values=ESO_VALUES,
            show_only=[CLUSTER_SECRET_STORE_TEMPLATE],
        )
        doc = docs[0]
        assert doc["metadata"]["name"] == "astronomer-cluster-secret-store"
        assert doc["spec"]["provider"]["aws"]["region"] == "us-east-2"

    def test_custom_name_and_region(self, kube_version):
        """ClusterSecretStore uses overridden name and region."""
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values={
                **ESO_VALUES,
                "external-secrets": {
                    "enabled": True,
                    "secretsBackend": {
                        "clusterSecretStore": {
                            "name": "my-custom-store",
                            "region": "eu-west-1",
                        },
                    },
                },
            },
            show_only=[CLUSTER_SECRET_STORE_TEMPLATE],
        )
        doc = docs[0]
        assert doc["metadata"]["name"] == "my-custom-store"
        assert doc["spec"]["provider"]["aws"]["region"] == "eu-west-1"

    def test_credentials_secret_refs(self, kube_version):
        """ClusterSecretStore references the correct credentials Secret name and namespace."""
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values={
                **ESO_VALUES,
                "external-secrets": {
                    "enabled": True,
                    "secretsBackend": {
                        "credentials": {
                            "name": "my-aws-creds",
                        },
                    },
                },
            },
            show_only=[CLUSTER_SECRET_STORE_TEMPLATE],
        )
        doc = docs[0]
        auth = doc["spec"]["provider"]["aws"]["auth"]["secretRef"]
        assert auth["accessKeyIDSecretRef"]["name"] == "my-aws-creds"
        assert auth["secretAccessKeySecretRef"]["name"] == "my-aws-creds"

    def test_metadata_namespace_matches_credentials_namespace(self, kube_version):
        """ClusterSecretStore metadata.namespace matches the credentials namespace."""
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values=ESO_VALUES,
            show_only=[CLUSTER_SECRET_STORE_TEMPLATE],
        )
        doc = docs[0]
        creds_namespace = doc["spec"]["provider"]["aws"]["auth"]["secretRef"]["accessKeyIDSecretRef"]["namespace"]
        assert doc["metadata"]["namespace"] == creds_namespace

    def test_aws_service_is_secrets_manager(self, kube_version):
        """ClusterSecretStore always targets SecretsManager."""
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values=ESO_VALUES,
            show_only=[CLUSTER_SECRET_STORE_TEMPLATE],
        )
        assert docs[0]["spec"]["provider"]["aws"]["service"] == "SecretsManager"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestSecretsBackendCredentials:
    def test_renders_in_data_plane_mode(self, kube_version):
        """Credentials Secret renders when plane.mode is 'data'."""
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values=ESO_VALUES,
            show_only=[SECRETS_BACKEND_CREDENTIALS_TEMPLATE],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["apiVersion"] == "v1"
        assert doc["kind"] == "Secret"
        assert doc["type"] == "Opaque"

    def test_not_rendered_outside_data_plane(self, kube_version):
        """Credentials Secret is not rendered when plane.mode is not 'data'."""
        for mode in ("control", "unified"):
            docs = render_chart(
                kube_version=kube_version,
                validate_objects=False,
                values={
                    "external-secrets": {"enabled": True},
                    "global": {"plane": {"mode": mode}},
                },
                show_only=[SECRETS_BACKEND_CREDENTIALS_TEMPLATE],
            )
            assert len(docs) == 0, f"Expected no credentials Secret in plane.mode={mode}"

    def test_default_name_and_namespace(self, kube_version):
        """Credentials Secret uses default name and namespace from values."""
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values=ESO_VALUES,
            show_only=[SECRETS_BACKEND_CREDENTIALS_TEMPLATE],
        )
        doc = docs[0]
        assert doc["metadata"]["name"] == "secrets-backend-credentials"
        assert doc["metadata"]["namespace"] == "default"

    def test_custom_name_and_namespace(self, kube_version):
        """Credentials Secret uses overridden name and namespace."""
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values={
                **ESO_VALUES,
                "external-secrets": {
                    "enabled": True,
                    "secretsBackend": {
                        "credentials": {
                            "name": "custom-creds",
                            "accessKey": "",
                            "secretAccessKey": "",
                        },
                    },
                },
            },
            show_only=[SECRETS_BACKEND_CREDENTIALS_TEMPLATE],
        )
        doc = docs[0]
        assert doc["metadata"]["name"] == "custom-creds"

    def test_credentials_are_base64_encoded(self, kube_version):
        """Access key and secret access key values are base64-encoded in the Secret data."""
        access_key = "AKIAIOSFODNN7EXAMPLE"
        secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values={
                **ESO_VALUES,
                "external-secrets": {
                    "enabled": True,
                    "secretsBackend": {
                        "credentials": {
                            "name": "secrets-backend-credentials",
                            "namespace": "astronomer",
                            "accessKey": access_key,
                            "secretAccessKey": secret_key,
                        },
                    },
                },
            },
            show_only=[SECRETS_BACKEND_CREDENTIALS_TEMPLATE],
        )
        doc = docs[0]
        expected_access_key = base64.b64encode(access_key.encode()).decode()
        expected_secret_key = base64.b64encode(secret_key.encode()).decode()
        assert doc["data"]["access-key"] == expected_access_key
        assert doc["data"]["secret-access-key"] == expected_secret_key

    def test_data_keys_present(self, kube_version):
        """Credentials Secret always contains the required data keys."""
        docs = render_chart(
            kube_version=kube_version,
            validate_objects=False,
            values=ESO_VALUES,
            show_only=[SECRETS_BACKEND_CREDENTIALS_TEMPLATE],
        )
        doc = docs[0]
        assert "access-key" in doc["data"]
        assert "secret-access-key" in doc["data"]
