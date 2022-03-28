from tests.helm_template_generator import render_chart
import pytest
from . import supported_k8s_versions
import jmespath
import yaml

standard_platform_repo = "quay.io/astronomer"
default_public_sidecar_repository_name = (
    f"{standard_platform_repo}/ap-auth-sidecar"
)


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
        assert doc["metadata"]["name"] == "RELEASE-NAME-alertmanager"
        assert doc["spec"]["template"]["spec"]["containers"][1]["name"] == "auth-proxy"

        assert jmespath.search("kind", docs[2]) == "Service"
        assert jmespath.search("metadata.name", docs[2]) == "RELEASE-NAME-alertmanager"
        assert jmespath.search("spec.type", docs[2]) == "ClusterIP"
        assert {
            "name": "auth-proxy",
            "protocol": "TCP",
            "port": 8084,
        } in jmespath.search("spec.ports", docs[2])

        assert "NetworkPolicy" == docs[3]["kind"]
        assert [{"port": 8084, "protocol": "TCP"}] == jmespath.search(
            "spec.ingress[*].ports[1]", docs[3]
        )

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
        assert doc["metadata"]["name"] == "RELEASE-NAME-prometheus"
        assert "auth-proxy" == doc["spec"]["template"]["spec"]["containers"][0]["name"]

        assert "Service" == jmespath.search("kind", docs[2])
        assert "RELEASE-NAME-prometheus" == jmespath.search("metadata.name", docs[2])
        assert "ClusterIP" == jmespath.search("spec.type", docs[2])
        assert {
            "name": "auth-proxy",
            "protocol": "TCP",
            "port": 8084,
        } in jmespath.search("spec.ports", docs[2])

        assert "NetworkPolicy" == docs[3]["kind"]
        assert [{"port": 8084, "protocol": "TCP"}] == jmespath.search(
            "spec.ingress[*].ports[1]", docs[3]
        )

    def test_authSidecar_kibana(self, kube_version):
        """Test Kibana Service with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"authSidecar": {"enabled": True}}},
            show_only=[
                "charts/kibana/templates/kibana-deployment.yaml",
                "charts/kibana/templates/kibana-auth-sidecar-configmap.yaml",
                "charts/kibana/templates/kibana-service.yaml",
                "charts/kibana/templates/kibana-networkpolicy.yaml",
                "charts/kibana/templates/ingress.yaml",
            ],
        )

        assert len(docs) == 5
        doc = docs[0]
        assert doc["kind"] == "Deployment"
        assert doc["apiVersion"] == "apps/v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-kibana"
        assert "auth-proxy" == doc["spec"]["template"]["spec"]["containers"][1]["name"]

        assert "Service" == jmespath.search("kind", docs[2])
        assert "RELEASE-NAME-kibana" == jmespath.search("metadata.name", docs[2])
        assert "ClusterIP" == jmespath.search("spec.type", docs[2])
        assert {
            "name": "auth-proxy",
            "protocol": "TCP",
            "port": 8084,
        } in jmespath.search("spec.ports", docs[2])

        assert "NetworkPolicy" == docs[3]["kind"]
        assert [
            {
                "namespaceSelector": {
                    "matchLabels": {"network.openshift.io/policy-group": "ingress"}
                }
            }
        ] == jmespath.search("spec.ingress[0].from", docs[3])
        assert [{"port": 8084, "protocol": "TCP"}] == jmespath.search(
            "spec.ingress[*].ports[0]", docs[3]
        )

    def test_authSidecar_houston_configmap_without_annotation(self, kube_version):
        """Test Houston Configmap with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"authSidecar": {"enabled": True, "tag": "placeholder-tag"}}
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        prod = yaml.safe_load(doc["data"]["production.yaml"])
        print(prod["deployments"]["authSideCar"])

        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-houston-config"

        expected_output = {
            "enabled": True,
            "repository": default_public_sidecar_repository_name,
            "tag": "placeholder-tag",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "annotations": {},
        }
        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_houston_configmap_with_annotation(self, kube_version):
        """Test Houston Configmap with authSidecar."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "authSidecar": {"enabled": True, "tag": "placeholder-tag"},
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

        assert len(docs) == 1
        doc = docs[0]
        prod = yaml.safe_load(doc["data"]["production.yaml"])
        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-houston-config"

        expected_output = {
            "enabled": True,
            "repository": default_public_sidecar_repository_name,
            "tag": "placeholder-tag",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "annotations": {
                "kubernetes.io/ingress.class": "astronomer-nginx",
                "nginx.ingress.kubernetes.io/proxy-body-size": "1024m",
            },
        }
        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_houston_configmap_with_private_registry(self, kube_version):
        """Test houston image obeys custom repository."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "authSidecar": {"enabled": True, "tag": "placeholder-tag"},
                    "privateRegistry": {
                        "enabled": True,
                        "repository": "some.registry.internal",
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        prod = yaml.safe_load(doc["data"]["production.yaml"])

        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-houston-config"

        expected_output = {
            "enabled": True,
            "repository": "some.registry.internal/ap-auth-sidecar",
            "tag": "placeholder-tag",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "annotations": {},
        }
        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_houston_configmap_honors_custom_sidecar_repository(
        self, kube_version
    ):
        """Test houston image obeys custom repository defined within global.sidecarLogging.repository"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "authSidecar": {
                        "enabled": True,
                        "tag": "placeholder-tag",
                        "repository": "different.repo/my-awesome-image",
                    }
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        prod = yaml.safe_load(doc["data"]["production.yaml"])

        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-houston-config"

        expected_output = {
            "enabled": True,
            "repository": "different.repo/my-awesome-image",
            "tag": "placeholder-tag",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "annotations": {},
        }
        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_houston_configmap_honors_privateRegistry_repository(
        self, kube_version
    ):
        """Test authSidecar prioritized honors a privateRegistry repository if defined"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "authSidecar": {
                        "enabled": True,
                        "tag": "placeholder-tag",
                    },
                    "privateRegistry": {
                        "enabled": True,
                        "repository": "some.registry.internal",
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        prod = yaml.safe_load(doc["data"]["production.yaml"])

        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-houston-config"

        expected_output = {
            "enabled": True,
            "repository": "some.registry.internal/ap-auth-sidecar",
            "tag": "placeholder-tag",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "annotations": {},
        }
        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_houston_configmap_prioritizes_authSidecar_repository_over_privateRegistry_repository(
        self, kube_version
    ):
        """Test authSidecar prioritized any repository image specified on authSidecar over the one on privateRegistry"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "authSidecar": {
                        "enabled": True,
                        "tag": "placeholder-tag",
                        "repository": "different.repo/my-awesome-image",
                    },
                    "privateRegistry": {
                        "enabled": True,
                        "repository": "some.registry.internal",
                    },
                }
            },
            show_only=[
                "charts/astronomer/templates/houston/houston-configmap.yaml",
            ],
        )

        assert len(docs) == 1
        doc = docs[0]

        prod = yaml.safe_load(doc["data"]["production.yaml"])

        assert doc["kind"] == "ConfigMap"
        assert doc["apiVersion"] == "v1"
        assert doc["metadata"]["name"] == "RELEASE-NAME-houston-config"

        expected_output = {
            "enabled": True,
            "repository": "different.repo/my-awesome-image",
            "tag": "placeholder-tag",
            "port": 8084,
            "pullPolicy": "IfNotPresent",
            "annotations": {},
        }
        assert expected_output == prod["deployments"]["authSideCar"]

    def test_authSidecar_repository_template_in_effect_on_grafana(self, kube_version):
        """Test authSidecar.image template modifies sidecar image value for grafana deployment"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "grafana": {"enabled": True},
                    "privateRegistry": {
                        "enabled": True,
                        "repository": "some.registry.internal",
                    },
                    "authSidecar": {"enabled": True, "tag": "placeholder-tag"},
                }
            },
        )

        doc = next(
            doc
            for doc in docs
            if doc["kind"] == "Deployment"
            and doc["metadata"]["name"] == "RELEASE-NAME-grafana"
        )
        container = next(
            container
            for container in doc["spec"]["template"]["spec"]["containers"]
            if container["name"] == "auth-proxy"
        )
        assert (
            container["image"]
            == "some.registry.internal/ap-auth-sidecar:placeholder-tag"
        )

    def test_authSidecar_repository_template_in_effect_on_kibana(self, kube_version):
        """Test authSidecar.image template modifies sidecar image value for kibana deployment"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "kibana": {"enabled": True},
                    "privateRegistry": {
                        "enabled": True,
                        "repository": "some.registry.internal",
                    },
                    "authSidecar": {"enabled": True, "tag": "placeholder-tag"},
                }
            },
        )

        doc = next(
            doc
            for doc in docs
            if doc["kind"] == "Deployment"
            and doc["metadata"]["name"] == "RELEASE-NAME-kibana"
        )
        container = next(
            container
            for container in doc["spec"]["template"]["spec"]["containers"]
            if container["name"] == "auth-proxy"
        )
        assert (
            container["image"]
            == "some.registry.internal/ap-auth-sidecar:placeholder-tag"
        )

    def test_authSidecar_repository_template_in_effect_on_prometheus(
        self, kube_version
    ):
        """Test authSidecar.image template modifies sidecar image value for prometheus stateful set"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "prometheus": {"enabled": True},
                    "privateRegistry": {
                        "enabled": True,
                        "repository": "some.registry.internal",
                    },
                    "authSidecar": {"enabled": True, "tag": "placeholder-tag"},
                }
            },
        )

        doc = next(
            doc
            for doc in docs
            if doc["kind"] == "StatefulSet"
            and doc["metadata"]["name"] == "RELEASE-NAME-prometheus"
        )
        container = next(
            container
            for container in doc["spec"]["template"]["spec"]["containers"]
            if container["name"] == "auth-proxy"
        )
        assert (
            container["image"]
            == "some.registry.internal/ap-auth-sidecar:placeholder-tag"
        )

    def test_authSidecar_repository_doesnt_use_disabled_private_registry(
        self, kube_version
    ):
        """Test authSidecar.image template doesnt use a value from privateRegistry when privateRegistry disabled"""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "prometheus": {"enabled": True},
                    "privateRegistry": {
                        "enabled": False,
                        "repository": "this-should-not-be-used",
                    },
                    "authSidecar": {"enabled": True, "tag": "placeholder-tag"},
                }
            },
        )

        doc = next(
            doc
            for doc in docs
            if doc["kind"] == "StatefulSet"
            and doc["metadata"]["name"] == "RELEASE-NAME-prometheus"
        )
        container = next(
            container
            for container in doc["spec"]["template"]["spec"]["containers"]
            if container["name"] == "auth-proxy"
        )
        public_image_name = f"{default_public_sidecar_repository_name}:placeholder-tag"
        assert container["image"] == public_image_name
