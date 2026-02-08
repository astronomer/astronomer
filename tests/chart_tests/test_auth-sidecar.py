import pytest
import yaml

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


def common_houston_config_test_cases(docs):
    """Test some things that should apply to all cases."""
    assert len(docs) == 1
    doc = docs[0]
    assert doc["kind"] == "ConfigMap"
    assert doc["apiVersion"] == "v1"
    assert doc["metadata"]["name"] == "release-name-houston-config"


default_resource = {"limits": {"cpu": "1000m", "memory": "1024Mi"}, "requests": {"cpu": "500m", "memory": "512Mi"}}


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAuthSidecar:
    def test_authSidecar_alertmanager(self, kube_version):
        """Test Alertmanager Service with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"authSidecar": {"enabled": True}}},
            show_only=[
                "charts/alertmanager/templates/alertmanager-statefulset.yaml",
                "charts/alertmanager/templates/alertmanager-auth-sidecar-configmap.yaml",
                "charts/alertmanager/templates/alertmanager-service.yaml",
                "charts/alertmanager/templates/alertmanager-networkpolicy.yaml",
                "charts/alertmanager/templates/ingress.yaml",
            ],
        )

        assert len(docs) == 5
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-alertmanager"
        assert doc["spec"]["template"]["spec"]["containers"][1]["name"] == "auth-proxy"
        assert doc["spec"]["template"]["spec"]["volumes"] == [
            {"name": "etc-ssl-certs", "emptyDir": {}},
            {"name": "nginx-write-dir", "emptyDir": {}},
            {"name": "nginx-run-dir", "emptyDir": {}},
            {"name": "alertmanager-sidecar-conf", "configMap": {"name": "release-name-alertmanager-nginx-conf"}},
            {
                "name": "config-volume",
                "configMap": {
                    "name": "release-name-alertmanager",
                    "items": [{"key": "alertmanager.yaml", "path": "alertmanager.yaml"}],
                },
            },
        ]

        assert "Service" == docs[2]["kind"]
        assert "release-name-alertmanager" == docs[2]["metadata"]["name"]
        assert "ClusterIP" == docs[2]["spec"]["type"]
        assert {
            "name": "auth-proxy",
            "protocol": "TCP",
            "port": 8084,
            "appProtocol": "tcp",
        } in docs[2]["spec"]["ports"]

        assert "NetworkPolicy" == docs[3]["kind"]
        assert any(x["ports"][1] == {"protocol": "TCP", "port": 8084} for x in docs[3]["spec"]["ingress"])

    def test_authSidecar_houston_with_custom_resources(self, kube_version):
        """Test custom resources are applied on Houston"""
        custom_resources = {
            "limits": {"cpu": "999m", "memory": "888Mi"},
            "requests": {"cpu": "777m", "memory": "666Mi"},
        }
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "authSidecar": {
                        "enabled": True,
                        "repository": "someregistry.io/my-custom-image",
                        "tag": "my-custom-tag",
                        "resources": custom_resources,
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        common_houston_config_test_cases(docs)
        prod = yaml.safe_load(docs[0]["data"]["production.yaml"])

        expected_output = {
            "enabled": True,
            "repository": "someregistry.io/my-custom-image",
            "ingressAllowedNamespaces": [],
            "tag": "my-custom-tag",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "annotations": {},
            "resources": custom_resources,
        }

        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_prometheus(self, kube_version):
        """Test Prometheus Service with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"authSidecar": {"enabled": True}}},
            show_only=[
                "charts/prometheus/templates/prometheus-statefulset.yaml",
                "charts/prometheus/templates/prometheus-auth-sidecar-configmap.yaml",
                "charts/prometheus/templates/prometheus-service.yaml",
                "charts/prometheus/templates/prometheus-networkpolicy.yaml",
                "charts/prometheus/templates/ingress.yaml",
            ],
        )

        assert len(docs) == 5
        doc = docs[0]
        assert doc["kind"] == "StatefulSet"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "release-name-prometheus"
        assert doc["spec"]["template"]["spec"]["volumes"] == [
            {"name": "nginx-write-dir", "emptyDir": {}},
            {"name": "nginx-run-dir", "emptyDir": {}},
            {"name": "prometheus-sidecar-conf", "configMap": {"name": "release-name-prometheus-nginx-conf"}},
            {
                "name": "federation-auth",
                "secret": {"secretName": "release-name-registry-auth-key", "items": [{"key": "token", "path": "federation-token"}]},
            },
            {
                "name": "prometheus-config-volume",
                "configMap": {"name": "release-name-prometheus-config", "items": [{"key": "config", "path": "prometheus.yaml"}]},
            },
            {
                "name": "alert-volume",
                "configMap": {"name": "release-name-prometheus-alerts", "items": [{"key": "alerts", "path": "alerts.yaml"}]},
            },
            {"name": "filesd", "emptyDir": {}},
            {"name": "etc-ssl-certs", "emptyDir": {}},
        ]
        assert "auth-proxy" == doc["spec"]["template"]["spec"]["containers"][0]["name"]

        assert "Service" == docs[2]["kind"]
        assert "release-name-prometheus" == docs[2]["metadata"]["name"]
        assert "ClusterIP" == docs[2]["spec"]["type"]
        assert {
            "name": "auth-proxy",
            "protocol": "TCP",
            "port": 8084,
            "appProtocol": "tcp",
        } in docs[2]["spec"]["ports"]

        assert "NetworkPolicy" == docs[3]["kind"]
        assert any(x["ports"][1] == {"protocol": "TCP", "port": 8084} for x in docs[3]["spec"]["ingress"])

    def test_authSidecar_houston_configmap_without_annotation(self, kube_version):
        """Test Houston Configmap with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "authSidecar": {
                        "enabled": True,
                        "repository": "someregistry.io/my-custom-image",
                        "tag": "my-custom-tag",
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        common_houston_config_test_cases(docs)

        prod = yaml.safe_load(docs[0]["data"]["production.yaml"])
        expected_output = {
            "enabled": True,
            "repository": "someregistry.io/my-custom-image",
            "ingressAllowedNamespaces": [],
            "tag": "my-custom-tag",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "resources": default_resource,
            "annotations": {},
        }
        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_houston_configmap_with_annotation(self, kube_version):
        """Test Houston Configmap with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "authSidecar": {
                        "enabled": True,
                        "repository": "someregistry.io/my-custom-image",
                        "tag": "my-custom-tag",
                    },
                    "extraAnnotations": {
                        "kubernetes.io/ingress.class": "astronomer-nginx",
                        "nginx.ingress.kubernetes.io/proxy-body-size": "1024m",
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        common_houston_config_test_cases(docs)
        prod = yaml.safe_load(docs[0]["data"]["production.yaml"])

        expected_output = {
            "enabled": True,
            "repository": "someregistry.io/my-custom-image",
            "ingressAllowedNamespaces": [],
            "tag": "my-custom-tag",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "resources": default_resource,
            "annotations": {
                "kubernetes.io/ingress.class": "astronomer-nginx",
                "nginx.ingress.kubernetes.io/proxy-body-size": "1024m",
            },
        }
        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_houston_configmap_with_securityContext(self, kube_version):
        """Test Houston Configmap with authSidecar securityContext."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "authSidecar": {
                        "enabled": True,
                        "repository": "someregistry.io/my-custom-image",
                        "tag": "my-custom-tag",
                        "securityContext": {"runAsUser": 1000},
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        common_houston_config_test_cases(docs)
        prod = yaml.safe_load(docs[0]["data"]["production.yaml"])
        expected_output = {
            "enabled": True,
            "ingressAllowedNamespaces": [],
            "repository": "someregistry.io/my-custom-image",
            "tag": "my-custom-tag",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "securityContext": {
                "runAsUser": 1000,
            },
            "resources": default_resource,
            "annotations": {},
        }
        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_houston_configmap_with_ingress_allowed_namespace(self, kube_version):
        """Test Houston Configmap with authSidecar ingressAllowedNamespaces."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "authSidecar": {
                        "enabled": True,
                        "ingressAllowedNamespaces": ["astronomer", "ingress"],
                        "repository": "someregistry.io/my-custom-image",
                        "tag": "my-custom-tag",
                        "securityContext": {"runAsUser": 1000},
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        common_houston_config_test_cases(docs)
        prod = yaml.safe_load(docs[0]["data"]["production.yaml"])
        expected_output = {
            "enabled": True,
            "ingressAllowedNamespaces": ["astronomer", "ingress"],
            "repository": "someregistry.io/my-custom-image",
            "tag": "my-custom-tag",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "securityContext": {
                "runAsUser": 1000,
            },
            "resources": default_resource,
            "annotations": {},
        }
        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_with_ingress_allowed_namespaces_empty(self, kube_version):
        """Test All Services with authSidecar and set no values in ingressAllowedNamespaces.
        Only include networkpolicies that have the network.openshift.io/policy-group: ingress label."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"authSidecar": {"enabled": True, "ingressAllowedNamespaces": []}}},
            show_only=[
                "charts/alertmanager/templates/alertmanager-networkpolicy.yaml",
                "charts/astronomer/templates/astro-ui/astro-ui-networkpolicy.yaml",
                "charts/astronomer/templates/houston/api/houston-networkpolicy.yaml",
                "charts/astronomer/templates/registry/registry-networkpolicy.yaml",
                "charts/grafana/templates/grafana-networkpolicy.yaml",
                "charts/prometheus/templates/prometheus-networkpolicy.yaml",
            ],
        )
        assert len(docs) == 6

        for doc in docs:
            assert "NetworkPolicy" == doc["kind"]
            namespaceSelectors = doc["spec"]["ingress"][0]["from"]
            assert {"namespaceSelector": {"matchLabels": {"network.openshift.io/policy-group": "ingress"}}} in namespaceSelectors

    def test_authSidecar_all_services_with_ingress_allowed_namespaces(self, kube_version):
        """Test All Services with authSidecar and allow some traffic namespaces.
        Only include networkpolicies that have the network.openshift.io/policy-group: ingress label"""

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"authSidecar": {"enabled": True, "ingressAllowedNamespaces": ["astro", "ingress-namespace"]}}},
            show_only=[
                "charts/alertmanager/templates/alertmanager-networkpolicy.yaml",
                "charts/astronomer/templates/astro-ui/astro-ui-networkpolicy.yaml",
                "charts/astronomer/templates/houston/api/houston-networkpolicy.yaml",
                "charts/astronomer/templates/registry/registry-networkpolicy.yaml",
                "charts/grafana/templates/grafana-networkpolicy.yaml",
                "charts/prometheus/templates/prometheus-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 6

        for doc in docs:
            assert "NetworkPolicy" == doc["kind"]
            namespaceSelectors = doc["spec"]["ingress"][0]["from"]
            assert {"namespaceSelector": {"matchLabels": {"network.openshift.io/policy-group": "ingress"}}} in namespaceSelectors
            assert {
                "namespaceSelector": {
                    "matchExpressions": [
                        {"key": "kubernetes.io/metadata.name", "operator": "In", "values": ["astro", "ingress-namespace"]}
                    ]
                }
            } in namespaceSelectors

    def test_commander_authSidecar_with_ingress_allowed_namespaces_empty_when_plane_mode_data(self, kube_version):
        """Test commander Services with authSidecar and set no values in ingressAllowedNamespaces.
        Only include networkpolicies that have the network.openshift.io/policy-group: ingress label."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}, "authSidecar": {"enabled": True, "ingressAllowedNamespaces": []}}},
            show_only=["charts/astronomer/templates/commander/commander-networkpolicy.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert "NetworkPolicy" == doc["kind"]
        namespaceSelectors = doc["spec"]["ingress"][0]["from"]
        assert {"namespaceSelector": {"matchLabels": {"network.openshift.io/policy-group": "ingress"}}} in namespaceSelectors

    def test_commander_authSidecar_with_ingress_allowed_namespaces(self, kube_version):
        """Test All Services with authSidecar and allow some traffic namespaces.
        Only include networkpolicies that have the network.openshift.io/policy-group: ingress label"""

        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                    "authSidecar": {"enabled": True, "ingressAllowedNamespaces": ["astro", "ingress-namespace"]},
                }
            },
            show_only=[
                "charts/astronomer/templates/commander/commander-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1

        doc = docs[0]
        assert "NetworkPolicy" == doc["kind"]
        namespaceSelectors = doc["spec"]["ingress"][0]["from"]
        assert {"namespaceSelector": {"matchLabels": {"network.openshift.io/policy-group": "ingress"}}} in namespaceSelectors
        assert {
            "namespaceSelector": {
                "matchExpressions": [
                    {"key": "kubernetes.io/metadata.name", "operator": "In", "values": ["astro", "ingress-namespace"]}
                ]
            }
        } in namespaceSelectors

    def test_commander_authSidecar_defaults(self, kube_version):
        """Test Commander authsidecar defaults"""

        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "plane": {"mode": "data"},
                }
            },
            show_only=[
                "charts/astronomer/templates/commander/commander-networkpolicy.yaml",
            ],
        )

        assert len(docs) == 1

        doc = docs[0]
        assert "NetworkPolicy" == doc["kind"]
        podSelectors = doc["spec"]["ingress"][0]["from"]
        assert {
            "podSelector": {"matchLabels": {"component": "dp-ingress-controller", "release": "release-name", "tier": "nginx"}}
        } in podSelectors
