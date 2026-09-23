from copy import deepcopy
from pathlib import Path

import jmespath
import pytest
from deepmerge import always_merger

from tests import git_root_dir, supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart


def _templates(subdir=""):
    root = Path(f"{git_root_dir}/charts/laminar/templates/{subdir}")
    found = sorted(str(x.relative_to(git_root_dir)) for x in root.glob("**/*.yaml") if not x.name.startswith("_"))
    assert found, f"no templates under {root}"
    return found


LAMINAR_TEMPLATES = _templates()
LAMINAR_HYPEVISOR_TEMPLATES = _templates("hypervisor")
LAMINAR_BOOTSTRAPPER_TEMPLATES = _templates("bootstrapper")
LAMINAR_ENV_CONFIGMAP_TEMPLATE = "charts/laminar/templates/configmap.yaml"

APISERVER_DEPLOYMENT_TEMPLATE = "charts/laminar/templates/apiserver/apiserver-deployment.yaml"
HYPERVISOR_DEPLOYMENT_TEMPLATE = "charts/laminar/templates/hypervisor/hypervisor-deployment.yaml"
BOOTSTRAPPER_ROLEBINDING_TEMPLATE = "charts/laminar/templates/bootstrapper/laminar-bootstrapper-rolebinding.yaml"

# The two pods laminar runs. Anything shared between them is parametrized over the pair rather
# than checked on one of them: each deployment template includes the shared pieces itself, so a
# template is free to forget one and a single-template test would not notice.
LAMINAR_DEPLOYMENTS = [
    pytest.param(APISERVER_DEPLOYMENT_TEMPLATE, "apiserver", id="apiserver"),
    pytest.param(HYPERVISOR_DEPLOYMENT_TEMPLATE, "hypervisor", id="hypervisor"),
]

BYO_BACKEND_SECRET = {"laminar": {"databaseBootstrapper": {"backendSecretName": "my-secret"}}}

EXPECTED_CONTAINER_SECURITY_CONTEXT = {
    "allowPrivilegeEscalation": False,
    "capabilities": {"drop": ["ALL"]},
    "readOnlyRootFilesystem": True,
    "runAsNonRoot": True,
    "runAsUser": 65534,
}


def laminar_values(*overrides, plane_mode="data"):
    """Return values that render laminar, with any overrides deep merged on top."""
    values = {"global": {"laminar": {"enabled": True}, "plane": {"mode": plane_mode}}}
    for override in overrides:
        always_merger.merge(values, deepcopy(override))
    return values


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestLaminar:
    def test_laminar_disabled_by_default(self, kube_version):
        """Test that laminar is disabled by default."""
        docs = render_chart(kube_version=kube_version)

        laminar_docs = [
            doc for doc in docs if str(doc.get("metadata", {}).get("labels", {}).get("chart", "")).startswith("laminar-")
        ]
        assert not laminar_docs

    @pytest.mark.parametrize("plane_mode", ["control", "unified"])
    def test_laminar_gated_by_plane_mode(self, kube_version, plane_mode):
        """Test that laminar renders only when the plane is data/unified."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"laminar": {"enabled": True}, "plane": {"mode": plane_mode}}},
            show_only=LAMINAR_TEMPLATES,
        )

        if plane_mode == "control":
            assert len(docs) == 0
        else:
            assert len(docs) > 0

    @pytest.mark.parametrize("plane_mode", ["unified", "data"])
    def test_laminar_hypervisor_defaults_when_enabled(self, kube_version, plane_mode):
        """Test that laminar renders only when the plane is data or unified."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"laminar": {"enabled": True}, "plane": {"mode": plane_mode}}},
            show_only=[*LAMINAR_HYPEVISOR_TEMPLATES, LAMINAR_ENV_CONFIGMAP_TEMPLATE],
        )
        assert len(docs) == 11
        hypervisor_deployment = docs[0]
        assert hypervisor_deployment["apiVersion"] == "apps/v1"
        assert hypervisor_deployment["metadata"]["name"] == "release-name-hypervisor"
        assert hypervisor_deployment["spec"]["template"]["spec"]["serviceAccountName"] == "release-name-hypervisor"
        c_by_name = get_containers_by_name(hypervisor_deployment, include_init_containers=True)
        assert set(c_by_name) == {"hypervisor", "laminar-bootstrapper"}
        assert c_by_name["hypervisor"]["securityContext"] == EXPECTED_CONTAINER_SECURITY_CONTEXT
        assert c_by_name["hypervisor"]["resources"] == {
            "requests": {"cpu": "200m", "memory": "256Mi"},
            "limits": {"cpu": "1", "memory": "1Gi"},
        }
        hypervisor_container_env = get_env_vars_dict(c_by_name["hypervisor"]["env"])
        assert hypervisor_container_env["LAMINAR_JWT_ISSUER"] == "https://houston.example.com/v2"
        assert hypervisor_container_env["LAMINAR_JWT_AUDIENCE"] == "laminar:api"

        hypervisor_service = docs[4]
        assert hypervisor_service["kind"] == "Service"
        assert hypervisor_service["metadata"]["name"] == "release-name-hypervisor"
        assert hypervisor_service["metadata"]["labels"] == {
            "component": "hypervisor",
            "release": "release-name",
            "chart": "laminar-0.12.0",
            "heritage": "Helm",
            "tier": "laminar",
            "plane": plane_mode,
            "app.kubernetes.io/name": "hypervisor",
        }
        assert hypervisor_service["spec"]["type"] == "ClusterIP"
        assert hypervisor_service["spec"]["ports"] == [
            {"name": "http", "protocol": "TCP", "port": 8000, "targetPort": "http", "appProtocol": "http"},
        ]
        volume_mount_search_result = jmespath.search(
            "spec.template.spec.containers[*].volumeMounts[?name == 'laminar-env']",
            docs[0],
        )
        expected_hypervisor_volume_mounts_result = [
            [
                {
                    "mountPath": "/laminar.env",
                    "name": "laminar-env",
                    "subPath": "laminar.env",
                    "readOnly": True,
                }
            ]
        ]
        assert volume_mount_search_result == expected_hypervisor_volume_mounts_result

        env_lines = docs[10]["data"]["laminar.env"].strip().splitlines()
        env_vars = dict(line.split("=", 1) for line in env_lines)
        assert env_vars == {
            "laminar_scaling__dry_run_strategy": "NEVER",
            "laminar_apply_custom_ddl": "True",
            "laminar_hypervisor__enable_healers": "False",
            "laminar_hypervisor__enable_health_incidents": "False",
            "laminar_hypervisor__configmap_metrics_enabled": "False",
            "laminar_hypervisor__configmap_metrics_use_informer": "False",
            "laminar_hypervisor__queued_task_second_threshold": "480",
            "laminar_hypervisor__disabled_metrics_csv": '""',
            "laminar_hypervisor__dry_run_healers_csv": "CatatonicWorkerTerminator",
        }

    @pytest.mark.parametrize("plane_mode", ["unified", "data"])
    def test_laminar_bootstrapper_rbac_objects(self, kube_version, plane_mode):
        """Test the RBAC that lets the bootstrapper write the backend secret.

        Helm installs a Role and a RoleBinding ahead of a Deployment, and an init container that
        starts before them simply retries, so these need no hook ordering of their own.
        """
        docs = render_chart(
            kube_version=kube_version,
            values=laminar_values(plane_mode=plane_mode),
            show_only=LAMINAR_BOOTSTRAPPER_TEMPLATES,
        )
        assert len(docs) == len(LAMINAR_BOOTSTRAPPER_TEMPLATES)
        by_kind = {doc["kind"]: doc for doc in docs}
        assert set(by_kind) == {"Role", "RoleBinding"}
        assert by_kind["Role"]["metadata"]["name"] == "release-name-laminar-bootstrapper-role"
        assert by_kind["Role"]["rules"] == [
            {"apiGroups": [""], "resources": ["secrets"], "verbs": ["list", "get", "create", "patch"]}
        ]

    @pytest.mark.parametrize("template,app_container", LAMINAR_DEPLOYMENTS)
    def test_laminar_bootstrapper_init_container(self, kube_version, template, app_container):
        """Test the bootstrapper init container that creates the laminar database.

        It runs on every pod start rather than once per release, so it has to stay idempotent, and
        it must not carry a startupProbe: Kubernetes rejects one on a non-sidecar init container,
        and the hook Job this replaced did define one.
        """
        docs = render_chart(kube_version=kube_version, values=laminar_values(), show_only=[template])

        assert len(docs) == 1
        pod_spec = docs[0]["spec"]["template"]["spec"]
        assert [container["name"] for container in pod_spec["initContainers"]] == ["laminar-bootstrapper"]
        bootstrapper = get_containers_by_name(docs[0], include_init_containers=True)["laminar-bootstrapper"]
        assert bootstrapper["image"].startswith("quay.io/astronomer/ap-db-bootstrapper:")
        assert bootstrapper["imagePullPolicy"] == "IfNotPresent"
        # Both pods size the bootstrapper from apiServer.resources, so on the hypervisor the init
        # container asks for more CPU (400m) than the hypervisor container it precedes (200m), and
        # the pod's effective request follows the larger of the two.
        assert bootstrapper["resources"] == {
            "requests": {"cpu": "400m", "memory": "256Mi"},
            "limits": {"cpu": "1", "memory": "1Gi"},
        }
        assert "startupProbe" not in bootstrapper
        assert get_env_vars_dict(bootstrapper["env"]) == {
            "BOOTSTRAP_DB": {"secretKeyRef": {"name": "astronomer-bootstrap", "key": "connection"}},
            "DB_NAME": "release-name-laminar",
            "SECRET_NAME": "release-name-laminar-backend",
            "NAMESPACE": "default",
            "IN_CLUSTER": "true",
        }

    @pytest.mark.parametrize("template,app_container", LAMINAR_DEPLOYMENTS)
    def test_laminar_bootstrapper_writes_the_secret_the_pod_reads(self, kube_version, template, app_container):
        """Test that the secret the bootstrapper creates is the one its own pod consumes.

        The two names are produced independently: SECRET_NAME on the init container, and the
        LAMINAR_DATABASE_URL secretKeyRef on the app container. Nothing in the chart forces them to
        agree. If they diverge the init container reports success and the app container waits on a
        secret that will never exist, so the pod sits in a CreateContainerConfigError loop with
        nothing in the release naming the cause.
        """
        docs = render_chart(kube_version=kube_version, values=laminar_values(), show_only=[template])

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0], include_init_containers=True)
        written = get_env_vars_dict(c_by_name["laminar-bootstrapper"]["env"])["SECRET_NAME"]
        read = get_env_vars_dict(c_by_name[app_container]["env"])["LAMINAR_DATABASE_URL"]["secretKeyRef"]["name"]
        assert written == read == "release-name-laminar-backend"

    def test_laminar_bootstrapper_rolebinding_names_the_running_service_accounts(self, kube_version):
        """Test that the RoleBinding grants the service accounts the component pods actually use.

        The bootstrapper has no pod, and so no service account, of its own any more: it inherits
        whichever one its host pod runs as. A subject naming anything else leaves it unable to
        create the backend secret, and the symptom is pods stuck in Init rather than a failed hook.
        """
        docs = render_chart(
            kube_version=kube_version,
            values=laminar_values(),
            show_only=[BOOTSTRAPPER_ROLEBINDING_TEMPLATE, APISERVER_DEPLOYMENT_TEMPLATE, HYPERVISOR_DEPLOYMENT_TEMPLATE],
        )

        assert len(docs) == 3
        rolebinding = next(doc for doc in docs if doc["kind"] == "RoleBinding")
        running = {doc["spec"]["template"]["spec"]["serviceAccountName"] for doc in docs if doc["kind"] == "Deployment"}
        assert {subject["name"] for subject in rolebinding["subjects"]} == running
        assert running == {"release-name-api-server", "release-name-hypervisor"}
        assert all(subject["kind"] == "ServiceAccount" for subject in rolebinding["subjects"])
        assert all(subject["namespace"] == "default" for subject in rolebinding["subjects"])
        assert rolebinding["roleRef"]["name"] == "release-name-laminar-bootstrapper-role"

    @pytest.mark.parametrize("template,app_container", LAMINAR_DEPLOYMENTS)
    def test_laminar_bootstrapper_skipped_with_byo_backend_secret(self, kube_version, template, app_container):
        """Test that a customer-supplied backend secret leaves no bootstrapper to run."""
        docs = render_chart(
            kube_version=kube_version,
            values=laminar_values(BYO_BACKEND_SECRET),
            show_only=[template],
        )

        assert len(docs) == 1
        assert "initContainers" not in docs[0]["spec"]["template"]["spec"]

    def test_laminar_bootstrapper_rbac_skipped_with_byo_backend_secret(self, kube_version):
        """Test that nothing is granted secret write in the namespace when nothing bootstraps.

        The hypervisor deployment is in show_only only to give helm a document to return: with the
        RBAC templates alone rendering empty, helm fails the whole command rather than returning
        nothing.
        """
        docs = render_chart(
            kube_version=kube_version,
            values=laminar_values(BYO_BACKEND_SECRET),
            show_only=[*LAMINAR_BOOTSTRAPPER_TEMPLATES, HYPERVISOR_DEPLOYMENT_TEMPLATE],
        )

        assert [doc["kind"] for doc in docs] == ["Deployment"]

    @pytest.mark.parametrize("template,app_container", LAMINAR_DEPLOYMENTS)
    def test_laminar_database_url_with_byo_backend_secret(self, kube_version, template, app_container):
        """Test that a supplied backend secret is the one laminar reads.

        A single value both skips the bootstrapper and names the secret. Were it only to do the
        first, laminar would go on reading the generated name that nothing now creates, and the
        pods would wait on a secret that never appears.
        """
        docs = render_chart(
            kube_version=kube_version,
            values=laminar_values(BYO_BACKEND_SECRET),
            show_only=[template],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name[app_container]["env"])
        assert env_vars["LAMINAR_DATABASE_URL"]["secretKeyRef"] == {"name": "my-secret", "key": "connection"}

    @pytest.mark.parametrize(
        "extra_values,expected_pull_secrets",
        [
            ({}, None),
            (
                {"laminar": {"imagePullSecrets": [{"name": "quay-pull-secret"}]}},
                [{"name": "quay-pull-secret"}],
            ),
            (
                {
                    "global": {
                        "privateRegistry": {
                            "enabled": True,
                            "repository": "my.registry/astro",
                            "secretName": "private-registry-secret",
                        }
                    },
                    "laminar": {"imagePullSecrets": [{"name": "quay-pull-secret"}]},
                },
                [{"name": "private-registry-secret"}],
            ),
        ],
        ids=["unset", "explicit", "private-registry-wins"],
    )
    def test_laminar_image_pull_secrets(self, kube_version, extra_values, expected_pull_secrets):
        """Test that every laminar pod gets the pull secret, and that privateRegistry takes precedence.

        Both templates are rendered together because the pull secret comes from a shared helper:
        testing one would prove the helper works while leaving the other free to forget to call it.

        The precedence case sets both sources at once. That combination is the one that silently
        pulls the wrong image if it ever inverts, because privateRegistry also rewrites the
        repository, so the secret and the image have to agree on which source won.
        """
        docs = render_chart(
            kube_version=kube_version,
            values=laminar_values(extra_values),
            show_only=[APISERVER_DEPLOYMENT_TEMPLATE, HYPERVISOR_DEPLOYMENT_TEMPLATE],
        )

        assert len(docs) == 2
        for doc in docs:
            pod_spec = doc["spec"]["template"]["spec"]
            assert pod_spec.get("imagePullSecrets") == expected_pull_secrets, (
                f"unexpected imagePullSecrets on {doc['kind']}/{doc['metadata']['name']}"
            )

    @pytest.mark.parametrize(
        "extra_values,expected_image",
        [
            (
                {"laminar": {"images": {"laminar": {"repository": "quay.io/astronomer/laminar", "tag": "1.0.0-rc1"}}}},
                "quay.io/astronomer/laminar:1.0.0-rc1",
            ),
            (
                {
                    "global": {"privateRegistry": {"enabled": True, "repository": "my.registry/astro"}},
                    "laminar": {"images": {"laminar": {"repository": "quay.io/astronomer/laminar", "tag": "1.0.0-rc1"}}},
                },
                "my.registry/astro/ap-laminar:1.0.0-rc1",
            ),
        ],
        ids=["explicit-repository", "private-registry-wins"],
    )
    def test_laminar_image_repository(self, kube_version, extra_values, expected_image):
        """Test which source names the laminar image.

        The two differ in more than the registry. privateRegistry appends a fixed `ap-laminar`,
        so it cannot express a repository that is not named that way, which is why an explicit
        repository exists at all. Pinning both spellings keeps that distinction from being
        refactored away.
        """
        docs = render_chart(
            kube_version=kube_version,
            values=laminar_values(extra_values),
            show_only=[APISERVER_DEPLOYMENT_TEMPLATE],
        )

        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        assert c_by_name["apiserver"]["image"] == expected_image
