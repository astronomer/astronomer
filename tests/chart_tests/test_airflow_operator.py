from pathlib import Path

import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils import get_containers_by_name
from tests.utils.chart import render_chart


def _is_operator_doc(doc):
    """True if a rendered doc belongs to the airflow-operator subchart.

    The tier=operator label alone is insufficient — the CRDs and the webhook
    configurations don't carry it — so match on all three signals the operator
    resources use: the tier label, the CRD name suffix, and the name markers.
    """
    metadata = doc.get("metadata", {})
    name = metadata.get("name", "")
    labels = metadata.get("labels") or {}
    if labels.get("tier") == "operator":
        return True
    if doc.get("kind") == "CustomResourceDefinition" and name.endswith(".airflow.apache.org"):
        return True
    return any(marker in name for marker in ("airflow-operator", "aocm", "aom-config", "runtime-version-config"))


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAirflowOperator:
    def test_airflow_operator_cert_manager(self, kube_version):
        """Test Airflow operator cert manager with flags."""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "airflow-operator": {
                    "certManager": {"enabled": True},
                },
                "global": {
                    "operator": {"enabled": True},
                },
            },
            show_only=sorted(
                [
                    str(x.relative_to(git_root_dir))
                    for x in Path(f"{git_root_dir}/charts/airflow-operator/templates/certmanager").glob("*")
                ]
            ),
        )
        assert len(docs) == 2
        assert "Issuer" == docs[0]["kind"]
        assert "Certificate" == docs[1]["kind"]
        assert "cert-manager.io/v1" == docs[0]["apiVersion"]
        assert "cert-manager.io/v1" == docs[1]["apiVersion"]
        assert "release-name-airflow-operator-serving-cert" == docs[1]["metadata"]["name"]
        assert "release-name-airflow-operator-selfsigned-issuer" == docs[0]["metadata"]["name"]

    def test_airflow_operator_crd(self, kube_version):
        """Test Airflow Operator crd template"""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "airflow-operator": {
                    "crd": {"create": True},
                },
                "global": {
                    "operator": {"enabled": True},
                },
            },
            show_only=sorted(
                [str(x.relative_to(git_root_dir)) for x in Path(f"{git_root_dir}/charts/airflow-operator/templates/crds").glob("*")]
            ),
        )
        assert len(docs) == 13
        for doc in docs:
            assert "apiextensions.k8s.io/v1" == doc["apiVersion"]
            assert "CustomResourceDefinition" == doc["kind"]
            assert "cert-manager.io/inject-ca-from" in doc["metadata"]["annotations"]
            assert "airflow.apache.org" in doc["metadata"]["name"]

    @pytest.mark.parametrize("crd_create", [True, False])
    def test_airflow_operator_crd_create_toggle(self, kube_version, crd_create):
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                },
                "airflow-operator": {
                    "crd": {"create": crd_create},
                },
            },
        )
        crds = [doc for doc in docs if doc.get("kind") == "CustomResourceDefinition"]
        if crd_create:
            assert len(crds) == 13
            for doc in crds:
                assert doc["metadata"]["name"].endswith(".airflow.apache.org")
        else:
            assert crds == [], f"expected no CRDs when crd.create is false, got: {[c['metadata']['name'] for c in crds]}"

    @pytest.mark.parametrize(
        "plane_mode,should_render",
        [
            ("data", True),
            ("unified", True),
            ("control", False),
        ],
    )
    def test_airflow_operator_renders(self, kube_version, plane_mode, should_render):
        """Operator resources only render on planes (data, unified), not on the control plane."""
        crd_templates = sorted(
            str(x.relative_to(git_root_dir)) for x in Path(f"{git_root_dir}/charts/airflow-operator/templates/crds").glob("*")
        )
        values = {
            "airflow-operator": {
                "crd": {"create": True},
            },
            "global": {
                "operator": {"enabled": True},
                "plane": {"mode": plane_mode},
            },
        }
        if should_render:
            docs = render_chart(
                validate_objects=False,
                kube_version=kube_version,
                values=values,
                show_only=crd_templates,
            )
            assert len(docs) == 13
            for doc in docs:
                assert "CustomResourceDefinition" == doc["kind"]
        else:
            # On the control plane the operator templates render empty. helm errors with
            # "could not find template" when --show-only targets an all-empty template, so
            # render the full chart and assert no operator CRDs are emitted.
            docs = render_chart(
                validate_objects=False,
                kube_version=kube_version,
                values=values,
            )
            operator_docs = [f"{doc.get('kind')}/{doc.get('metadata', {}).get('name')}" for doc in docs if _is_operator_doc(doc)]
            assert operator_docs == [], f"control plane must not render operator resources, got: {operator_docs}"

    def test_airflow_operator_secret(self, kube_version):
        """Test Airflow Operator Webhook tls"""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "airflow-operator": {
                    "webhooks": {
                        "useCustomTlsCerts": True,
                        "caBundle": "abc123",
                        "tlsCert": "tlscert123",
                        "tlsKey": "tlskey123",
                    },
                },
                "global": {
                    "operator": {"enabled": True},
                },
            },
            show_only=["charts/airflow-operator/templates/secrets/webhooks-tls.yaml"],
        )

        assert len(docs) == 1
        assert "v1" in docs[0]["apiVersion"]
        assert "Secret" in docs[0]["kind"]
        assert "release-name-webhooks-tls-certs" in docs[0]["metadata"]["name"]
        assert "kubernetes.io/tls" in docs[0]["type"]
        expected_data = {"tls.crt": "dGxzY2VydDEyMw==", "tls.key": "dGxza2V5MTIz"}
        assert docs[0]["data"] == expected_data

    def test_airflow_operator_webhooks(self, kube_version):
        """Test Airflow Operator Webhook tls"""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                },
                "airflow-operator": {"webhooks": {"enabled": True}},
            },
            show_only=sorted(
                [
                    str(x.relative_to(git_root_dir))
                    for x in Path(f"{git_root_dir}/charts/airflow-operator/templates/webhooks").glob("*")
                ]
            ),
        )
        assert len(docs) == 2
        assert "admissionregistration.k8s.io/v1" == docs[0]["apiVersion"]
        assert "MutatingWebhookConfiguration" == docs[0]["kind"]
        assert "ValidatingWebhookConfiguration" == docs[1]["kind"]
        assert "release-name-airflow-operator-mutating-webhook-configuration" == docs[0]["metadata"]["name"]
        assert "release-name-airflow-operator-validating-webhook-configuration" == docs[1]["metadata"]["name"]

    def test_airflow_operator_airgap(self, kube_version):
        """""Test Airflow Operator airgapped mode""" ""
        runtime_releases_json = {
            "runtimeVersions": {
                "4.2.5": {"metadata": {"airflowVersion": "2.4.2", "channel": "stable", "releaseDate": "2023-01-15"}},
                "5.0.0": {"metadata": {"airflowVersion": "2.5.0", "channel": "stable", "releaseDate": "2023-03-20"}},
            }
        }
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                },
                "airflow-operator": {"airgapped": True, "runtimeVersions": {"versionsJson": runtime_releases_json}},
            },
            show_only=["charts/airflow-operator/templates/configmap/runtime-versions.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["apiVersion"] == "v1"
        assert doc["data"]["versions.json"] == runtime_releases_json
        assert doc["kind"] == "ConfigMap"
        assert doc["metadata"]["name"] == "release-name-runtime-version-config"
        assert doc["metadata"]["labels"]["tier"] == "operator"

    def test_airflow_operator_manager_defaults(self, kube_version):
        """Test Airflow Operator manager defaults"""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                },
                "airflow-operator": {
                    "manager": {
                        "metrics": {
                            "enabled": True,
                        }
                    },
                    "webhooks": {"enabled": True},
                },
            },
            show_only=sorted(
                [
                    str(x.relative_to(git_root_dir))
                    for x in Path(f"{git_root_dir}/charts/airflow-operator/templates/manager").glob("*")
                ]
            ),
        )
        assert len(docs) == 5
        assert docs[0]["apiVersion"] == "apps/v1"
        assert docs[0]["kind"] == "Deployment"
        assert docs[0]["metadata"]["name"] == "release-name-aocm"
        assert docs[1]["kind"] == "Service"
        assert docs[1]["metadata"]["name"] == "release-name-aocm-metrics-service"
        assert docs[2]["kind"] == "NetworkPolicy"
        assert docs[2]["metadata"]["name"] == "release-name-airflow-operator-policy"
        assert docs[3]["kind"] == "ConfigMap"
        assert docs[3]["metadata"]["name"] == "release-name-aom-config"
        assert docs[4]["kind"] == "Service"
        assert docs[4]["metadata"]["name"] == "release-name-airflow-operator-webhook-service"
        assert docs[0]["metadata"]["labels"]["component"] == "controller-manager"
        assert docs[1]["metadata"]["labels"]["component"] == "controller-manager"

        # Render the full chart (not --show-only): with webhooks disabled some manager
        # templates render empty, and helm errors when --show-only targets an all-empty
        # template. Assert the webhook service is simply absent from the output.
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                },
                "airflow-operator": {
                    "webhooks": {"enabled": False},
                },
            },
        )
        webhook_services = [doc for doc in docs if "webhook" in doc.get("metadata", {}).get("name", "")]
        assert len(webhook_services) == 0

    def test_airflow_operator_manager_metrics_enabled(self, kube_version):
        """Test Airflow Operator manager with metrics endpoints enabled"""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                },
                "airflow-operator": {
                    "manager": {
                        "metrics": {
                            "enabled": True,
                        }
                    }
                },
            },
            show_only=[
                "charts/airflow-operator/templates/manager/controller-manager-deployment.yaml",
                "charts/airflow-operator/templates/manager/controller-manager-metrics-service.yaml",
            ],
        )
        assert len(docs) == 2
        c_by_name = get_containers_by_name(docs[0], include_init_containers=False)
        assert "manager" in c_by_name["manager"]["name"]
        assert "--metrics-bind-address=127.0.0.1:8080" in c_by_name["manager"]["args"]
        assert "/manager" in c_by_name["manager"]["command"]
        doc = docs[1]
        assert doc["kind"] == "Service"
        assert doc["metadata"]["name"] == "release-name-aocm-metrics-service"
        assert doc["spec"]["selector"]["component"] == "controller-manager"
        assert doc["spec"]["type"] == "ClusterIP"
        assert doc["spec"]["ports"] == [
            {
                "port": 8443,
                "targetPort": 8080,
                "protocol": "TCP",
                "name": "metrics",
                "appProtocol": "http",
            }
        ]

    def test_airflow_operator_manager_environment_default(self, kube_version):
        """Test the manager container has AIRFLOW_OPERATOR_ENVIRONMENT set to 'apc'."""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                },
            },
            show_only=[
                "charts/airflow-operator/templates/manager/controller-manager-deployment.yaml",
            ],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0], include_init_containers=False)
        env = {e["name"]: e["value"] for e in c_by_name["manager"]["env"]}
        assert env["AIRFLOW_OPERATOR_ENVIRONMENT"] == "apc"

    def test_airflow_operator_manager_private_registry(self, kube_version):
        """Test the manager uses the private registry image and imagePullSecrets when global privateRegistry is enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                    "privateRegistry": {
                        "enabled": True,
                        "repository": "my.private.registry/astronomer",
                        "secretName": "my-registry-secret",
                    },
                },
            },
            show_only=[
                "charts/airflow-operator/templates/manager/controller-manager-deployment.yaml",
            ],
        )
        assert len(docs) == 1
        pod_spec = docs[0]["spec"]["template"]["spec"]
        assert pod_spec["imagePullSecrets"] == [{"name": "my-registry-secret"}]
        c_by_name = get_containers_by_name(docs[0], include_init_containers=False)
        image = c_by_name["manager"]["image"]
        # When privateRegistry is enabled the image is built from the private repo + the dev image name.
        assert image.startswith("my.private.registry/astronomer/airflow-operator-dev:")

    @pytest.mark.parametrize(
        "operator_enabled,np_enabled,should_render",
        [
            (True, True, True),
            (True, False, False),
            (False, True, False),
            (False, False, False),
        ],
    )
    def test_airflow_operator_networkpolicy_renders(self, kube_version, operator_enabled, np_enabled, should_render):
        """The operator NetworkPolicy renders only when both the operator and global networkPolicy are enabled."""
        np_file = "charts/airflow-operator/templates/manager/controller-manager-networkpolicy.yaml"
        values = {
            "global": {
                "operator": {"enabled": operator_enabled},
                "networkPolicy": {"enabled": np_enabled},
            },
        }
        if should_render:
            docs = render_chart(
                validate_objects=False,
                kube_version=kube_version,
                values=values,
                show_only=[np_file],
            )
            assert len(docs) == 1
            assert docs[0]["kind"] == "NetworkPolicy"
            assert docs[0]["apiVersion"] == "networking.k8s.io/v1"
            assert docs[0]["metadata"]["name"] == "release-name-airflow-operator-policy"
        else:
            # When the policy is gated off the template renders empty; helm errors when
            # --show-only targets an all-empty template, so render the full chart and
            # assert no operator NetworkPolicy is emitted.
            docs = render_chart(
                validate_objects=False,
                kube_version=kube_version,
                values=values,
            )
            operator_policies = [
                doc
                for doc in docs
                if doc.get("kind") == "NetworkPolicy"
                and doc.get("metadata", {}).get("name", "") == "release-name-airflow-operator-policy"
            ]
            assert operator_policies == []

    def test_airflow_operator_networkpolicy_ingress_rules(self, kube_version):
        """The operator NetworkPolicy exposes the webhook port and allows prometheus to scrape the manager."""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                    "networkPolicy": {"enabled": True},
                },
            },
            show_only=["charts/airflow-operator/templates/manager/controller-manager-networkpolicy.yaml"],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["spec"]["policyTypes"] == ["Ingress"]
        assert doc["spec"]["podSelector"]["matchLabels"] == {
            "tier": "operator",
            "component": "controller-manager",
            "release": "release-name",
        }

        ingress = doc["spec"]["ingress"]
        assert len(ingress) == 2

        # First rule: webhook port open to any source (no "from" restriction).
        webhook_rule = ingress[0]
        assert "from" not in webhook_rule
        assert webhook_rule["ports"] == [{"protocol": "TCP", "port": 9443}]

        # Second rule: prometheus may scrape the manager upstream metrics port.
        prometheus_rule = ingress[1]
        assert prometheus_rule["ports"] == [{"protocol": "TCP", "port": 8080}]
        assert prometheus_rule["from"] == [
            {
                "podSelector": {
                    "matchLabels": {
                        "tier": "monitoring",
                        "component": "prometheus",
                        "release": "release-name",
                    }
                }
            }
        ]

    def test_operator_resource_names_within_dns_limits(self, kube_version):
        """Operator resource names must stay within k8s name limits with a long release name.

        The manager Deployment/Service/ConfigMap/ServiceAccount names were deliberately
        shortened (e.g. -aocm, -aom-config) so they don't consume a customer's release-name
        headroom against the 63-char DNS-label limit that k8s/helm enforce. This guards
        against an upstream chart sync silently re-lengthening them (see review on commit
        44e45982). The webhook Service keeps the longest release-prefixed suffix
        (-airflow-operator-webhook-service, 33 chars), so a 30-char release name must still
        leave its name <= 63 (33 + 30 = 63).
        """
        long_release_name = "a" * 30
        show_only = [
            "charts/airflow-operator/templates/manager/controller-manager-deployment.yaml",
            "charts/airflow-operator/templates/manager/controller-manager-metrics-service.yaml",
            "charts/airflow-operator/templates/manager/manager-config-configmap.yaml",
            "charts/airflow-operator/templates/manager/webhook-service.yaml",
            "charts/airflow-operator/templates/rbac/controller-manager-serviceaccount.yaml",
            "charts/airflow-operator/templates/rbac/leader-election-role.yaml",
            "charts/airflow-operator/templates/rbac/leader-election-rolebinding.yaml",
            "charts/airflow-operator/templates/certmanager/selfsigned-issuer.yaml",
            "charts/airflow-operator/templates/certmanager/serving-cert-certificate.yaml",
            "charts/airflow-operator/templates/webhooks/mutating-webhook-configuration.yaml",
            "charts/airflow-operator/templates/webhooks/validating-webhook-configuration.yaml",
        ]
        docs = render_chart(
            name=long_release_name,
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                },
                "airflow-operator": {
                    "manager": {"metrics": {"enabled": True}},
                    "webhooks": {"enabled": True},
                    "certManager": {"enabled": True},
                },
            },
            show_only=show_only,
        )
        assert docs, "expected operator resources to render"
        for doc in docs:
            name = doc["metadata"]["name"]
            # Service names become DNS labels (63-char cap); other resource names are
            # DNS subdomains (253-char cap).
            limit = 63 if doc["kind"] == "Service" else 253
            assert len(name) <= limit, f"{doc['kind']}/{name} is {len(name)} chars, exceeds {limit}"

    def test_operator_resource_names_are_release_prefixed(self, kube_version):
        release = "custom-rel"
        show_only = [
            "charts/airflow-operator/templates/manager/controller-manager-deployment.yaml",
            "charts/airflow-operator/templates/manager/controller-manager-metrics-service.yaml",
            "charts/airflow-operator/templates/secrets/webhooks-tls.yaml",
        ]
        docs = render_chart(
            name=release,
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                },
                "airflow-operator": {
                    "manager": {"metrics": {"enabled": True}},
                    "webhooks": {
                        "useCustomTlsCerts": True,
                        "caBundle": "abc123",
                        "tlsCert": "tlscert123",
                        "tlsKey": "tlskey123",
                    },
                },
            },
            show_only=show_only,
        )
        names_by_kind = {doc["kind"]: doc["metadata"]["name"] for doc in docs}
        assert names_by_kind["Deployment"] == f"{release}-aocm"
        assert names_by_kind["Service"] == f"{release}-aocm-metrics-service"
        assert names_by_kind["Secret"] == f"{release}-webhooks-tls-certs"
        for kind, name in names_by_kind.items():
            assert name.startswith(f"{release}-"), f"{kind}/{name} is not prefixed by the release name"

    @pytest.mark.parametrize("openshift_enabled", [True, False])
    def test_airflow_operator_openshift_flag(self, kube_version, openshift_enabled):
        """global.openshift.enabled must propagate to the manager as the --openshift arg."""
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values={
                "global": {
                    "operator": {"enabled": True},
                    "openshift": {"enabled": openshift_enabled},
                },
            },
            show_only=["charts/airflow-operator/templates/manager/controller-manager-deployment.yaml"],
        )
        assert len(docs) == 1
        args = get_containers_by_name(docs[0], include_init_containers=False)["manager"]["args"]
        assert ("--openshift" in args) is openshift_enabled

    @pytest.mark.parametrize(
        "sa_create,rbac_enabled,expected_sa_name,sa_object_rendered",
        [
            (True, True, "release-name-aocm", True),
            (True, False, "default", False),
            (False, True, "default", False),
            (False, False, "default", False),
        ],
    )
    def test_airflow_operator_serviceaccount_name(
        self, kube_version, sa_create, rbac_enabled, expected_sa_name, sa_object_rendered
    ):
        values = {
            "global": {
                "operator": {"enabled": True},
                "rbac": {"enabled": rbac_enabled},
            },
            "airflow-operator": {
                "serviceAccount": {"create": sa_create},
            },
        }
        # Full-chart render: when the SA template gates off it renders empty, and
        # --show-only errors on an all-empty template.
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values=values,
        )
        deployment = next(
            doc for doc in docs if doc.get("kind") == "Deployment" and doc.get("metadata", {}).get("name") == "release-name-aocm"
        )
        assert deployment["spec"]["template"]["spec"]["serviceAccountName"] == expected_sa_name

        operator_sas = [
            doc
            for doc in docs
            if doc.get("kind") == "ServiceAccount" and doc.get("metadata", {}).get("name") == "release-name-aocm"
        ]
        assert bool(operator_sas) is sa_object_rendered

    @pytest.mark.parametrize(
        "operator_values",
        [
            pytest.param({"global": {"operator": {"enabled": False}}}, id="explicitly-disabled"),
            pytest.param({}, id="default-unset"),
        ],
    )
    def test_airflow_operator_disabled_renders_nothing(self, kube_version, operator_values):
        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values=operator_values,
        )
        operator_docs = [f"{doc.get('kind')}/{doc.get('metadata', {}).get('name')}" for doc in docs if _is_operator_doc(doc)]
        assert operator_docs == [], f"expected no operator resources when disabled, got: {operator_docs}"

    @pytest.mark.parametrize(
        "airflow_operator_values,global_enabled,should_render",
        [
            # subchart flag unset -> global flag decides
            pytest.param({}, True, True, id="subchart-unset-global-true"),
            pytest.param({}, False, False, id="subchart-unset-global-false"),
            # subchart flag set -> it wins over the global flag (first-found-wins condition)
            pytest.param({"enabled": True}, True, True, id="subchart-true-global-true"),
            pytest.param({"enabled": False}, True, False, id="subchart-false-global-true"),
            pytest.param({"enabled": True}, False, False, id="subchart-true-global-false"),
            pytest.param({"enabled": False}, False, False, id="subchart-false-global-false"),
        ],
    )
    def test_airflow_operator_subchart_flag_precedence(self, kube_version, airflow_operator_values, global_enabled, should_render):
        values = {
            "global": {
                "operator": {"enabled": global_enabled},
                "plane": {"mode": "unified"},
            },
        }
        if airflow_operator_values:
            values["airflow-operator"] = airflow_operator_values

        docs = render_chart(
            validate_objects=False,
            kube_version=kube_version,
            values=values,
        )
        operator_docs = [doc for doc in docs if _is_operator_doc(doc)]
        if should_render:
            kinds = {doc["kind"] for doc in operator_docs}
            assert "Deployment" in kinds, f"operator rendered without the controller Deployment: {sorted(kinds)}"
            assert "CustomResourceDefinition" in kinds
        else:
            names = [f"{doc['kind']}/{doc['metadata']['name']}" for doc in operator_docs]
            assert names == [], f"expected no operator resources, got: {names}"
