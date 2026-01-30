import json

import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestIngress:
    labels = {"type": "apps"}

    def test_basic_ingress(self, kube_version):
        # sourcery skip: extract-duplicate-method
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/ingress.yaml"],
        )

        assert len(docs) == 1

        doc = docs[0]

        assert len(doc["metadata"]["annotations"]) == 3

        assert doc["spec"]["rules"] == json.loads(
            """
            [{"host":"example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":
            "release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}},{"host":"app.example.com","http":{"paths":[{"path":"/",
            "pathType":"Prefix","backend":{"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}},{"host":
            "registry.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":
            "release-name-registry","port":{"name":"registry-http"}}}}]}}]
            """
        )

    def test_basic_ingress_with_labels(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/astronomer/templates/ingress.yaml"],
            values={"global": {"podLabels": self.labels}},
        )

        assert len(docs) == 1

        doc = docs[0]
        assert self.labels.items() <= doc["metadata"]["labels"].items()

    @pytest.mark.parametrize(
        ("mode", "expected"),
        [("control", True), ("data", False), ("unified", True)],
    )
    def test_astro_ui_per_host_ingress(self, mode, expected, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"enablePerHostIngress": True, "plane": {"mode": mode}, "podLabels": self.labels}},
            show_only=[
                "charts/astronomer/templates/astro-ui/astro-ui-ingress.yaml",
                "charts/astronomer/templates/ingress.yaml",
            ],
        )
        if expected:
            assert len(docs) == 2
            assert docs[0]["spec"]["rules"] == json.loads(
                """
                [{"host":"app.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":
                {"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}}]
                """
            )
            assert self.labels.items() <= docs[0]["metadata"]["labels"].items()
            assert docs[1]["spec"]["rules"] == json.loads(
                """
                [{"host":"example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":
                {"service":{"name":"release-name-astro-ui","port":{"name":"astro-ui-http"}}}}]}}]
                """
            )
            assert self.labels.items() <= docs[1]["metadata"]["labels"].items()
        else:
            assert not docs

    def test_registry_per_host_ingress(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"enablePerHostIngress": True}},
            show_only=[
                "charts/astronomer/templates/registry/registry-ingress.yaml",
                "charts/astronomer/templates/ingress.yaml",
            ],
        )
        assert len(docs) == 1
        expected_rules_v1 = json.loads(
            """
            [{"host":"registry.example.com","http":{"paths":[{"path":"/","pathType":"Prefix","backend":
            {"service":{"name":"release-name-registry","port":{"name":"registry-http"}}}}]}}]
            """
        )
        assert docs[0]["spec"]["rules"] == expected_rules_v1

    def test_single_ingress_per_host(self, kube_version):
        default_docs = render_chart(values={"global": {"enablePerHostIngress": True, "podLabels": self.labels}})
        ingresses = [doc for doc in default_docs if doc["kind"].lower() == "Ingress".lower()]
        assert len(ingresses) == 8
        assert all(len(doc["spec"]["rules"]) == 1 for doc in ingresses)
        assert all(len(doc["spec"]["tls"][0]["hosts"]) == 1 for doc in ingresses)
        assert all(doc["apiVersion"] == "networking.k8s.io/v1" for doc in ingresses)
        assert all(doc["kind"] == "Ingress" for doc in ingresses)
        assert all(doc["metadata"]["annotations"]["kubernetes.io/ingress.class"] == "release-name-nginx" for doc in ingresses)
        assert all(self.labels.items() <= doc["metadata"]["labels"].items() for doc in ingresses if doc["metadata"].get("labels"))

    def test_prometheus_federate_ingress(self, kube_version):
        """Test prometheus federate ingress configuration"""
        docs = render_chart(
            kube_version=kube_version,
            show_only=["charts/prometheus/templates/ingress.yaml", "charts/prometheus/templates/prometheus-federate-ingress.yaml"],
            values={"global": {"baseDomain": "example.com", "plane": {"mode": "data"}}},
        )

        assert len(docs) == 2

        federate_ingress = next((doc for doc in docs if "federate-ingress" in doc["metadata"]["name"]), None)
        assert federate_ingress is not None

        assert federate_ingress["kind"] == "Ingress"
        assert federate_ingress["apiVersion"] == "networking.k8s.io/v1"

        annotations = federate_ingress["metadata"]["annotations"]
        auth_annotations = ["nginx.ingress.kubernetes.io/auth-signin", "nginx.ingress.kubernetes.io/auth-response-headers"]
        for auth_annotation in auth_annotations:
            assert auth_annotation not in annotations

        rules = federate_ingress["spec"]["rules"]
        assert len(rules) == 1
        paths = rules[0]["http"]["paths"]
        assert len(paths) == 1
        assert paths[0]["path"] == "/"
        assert paths[0]["pathType"] == "Prefix"

        backend = paths[0]["backend"]
        assert backend["service"]["port"]["name"] == "http"

    def test_registry_ingress_control_vs_unified_plane(self, kube_version):
        """Test that registry.baseDomain is only exposed in unified plane mode"""
        # Test control plane mode - registry should NOT be present
        control_docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=["charts/astronomer/templates/ingress.yaml"],
        )

        assert len(control_docs) == 1
        control_doc = control_docs[0]

        # Assert registry is NOT in the rules
        hosts = [rule["host"] for rule in control_doc["spec"]["rules"]]
        assert "registry.example.com" not in hosts
        assert "example.com" in hosts
        assert "app.example.com" in hosts

        # Assert registry is NOT in TLS hosts
        tls_hosts = control_doc["spec"]["tls"][0]["hosts"]
        assert "registry.example.com" not in tls_hosts
        assert "example.com" in tls_hosts
        assert "app.example.com" in tls_hosts

        # Test unified plane mode - registry SHOULD be present
        unified_docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "unified"}}},
            show_only=["charts/astronomer/templates/ingress.yaml"],
        )

        assert len(unified_docs) == 1
        unified_doc = unified_docs[0]

        # Assert registry IS in the rules
        hosts = [rule["host"] for rule in unified_doc["spec"]["rules"]]
        assert "registry.example.com" in hosts
        assert "example.com" in hosts
        assert "app.example.com" in hosts

        # Assert registry IS in TLS hosts
        tls_hosts = unified_doc["spec"]["tls"][0]["hosts"]
        assert "registry.example.com" in tls_hosts
        assert "example.com" in tls_hosts
        assert "app.example.com" in tls_hosts

    @pytest.mark.parametrize(
        ("mode", "expected_astro_ui", "expected_registry", "expected_rule_count", "expected_hosts"),
        [
            ("control", True, False, 2, ["example.com", "app.example.com"]),
            ("data", False, True, 1, ["registry.dp01.example.com"]),
            ("unified", True, True, 3, ["example.com", "app.example.com", "registry.example.com"]),
        ],
    )
    def test_ingress_per_plane_mode(
        self, mode, expected_astro_ui, expected_registry, expected_rule_count, expected_hosts, kube_version
    ):
        """Test ingress configuration for all plane modes"""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": mode, "domainPrefix": "dp01"}}},
            show_only=["charts/astronomer/templates/ingress.yaml"],
        )

        assert len(docs) == 1, f"Expected 1 ingress for {mode} mode"
        doc = docs[0]

        # Check rule count
        assert len(doc["spec"]["rules"]) == expected_rule_count, f"Expected {expected_rule_count} rules for {mode} mode"

        # Check hosts in rules
        hosts = [rule["host"] for rule in doc["spec"]["rules"]]
        assert set(hosts) == set(expected_hosts), f"Expected hosts {expected_hosts} for {mode} mode, got {hosts}"

        # Check TLS hosts
        tls_hosts = doc["spec"]["tls"][0]["hosts"]
        for expected_host in expected_hosts:
            assert expected_host in tls_hosts, f"Expected {expected_host} in TLS hosts for {mode} mode"

        # install.example.com should never be in TLS #6611
        assert "install.example.com" not in tls_hosts

        # Check nginx configuration snippet (should be present in control/unified, not needed in data)
        annotations = doc["metadata"]["annotations"]
        if expected_astro_ui:
            assert "nginx.ingress.kubernetes.io/configuration-snippet" in annotations
            assert "app.example.com" in annotations["nginx.ingress.kubernetes.io/configuration-snippet"]
