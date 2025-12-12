import re

import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestPrometheusFederationAuthConfigMap:
    def test_prometheus_federation_auth_configmap_defaults(self, kube_version):
        """Test the default configuration of the Prometheus Federation Auth ConfigMap."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        configmap = docs[0]
        assert configmap["kind"] == "ConfigMap"
        assert configmap["metadata"]["name"].endswith("-federation-auth-config")

        # Verify labels
        labels = configmap["metadata"]["labels"]
        assert labels["tier"] == "monitoring"
        assert labels["component"] == "prometheus-federation-auth"
        assert "release" in labels
        assert "chart" in labels
        assert "heritage" in labels

        # Verify nginx.conf exists
        assert "nginx.conf" in configmap["data"]
        assert configmap["data"]["nginx.conf"] is not None

    def test_prometheus_federation_auth_configmap_not_created_in_control_mode(self, kube_version):
        """Test that the ConfigMap is not created when plane mode is control."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 0

    def test_prometheus_federation_auth_configmap_nginx_conf_structure(self, kube_version):
        """Test the nginx configuration structure."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Verify essential nginx directives
        assert "worker_processes" in nginx_conf
        assert "events {" in nginx_conf
        assert "http {" in nginx_conf
        assert "upstream prometheus_backend {" in nginx_conf
        assert "server {" in nginx_conf
        assert "pid /tmp/nginx.pid;" in nginx_conf
        assert "worker_connections 1024" in nginx_conf

    def test_prometheus_federation_auth_configmap_lua_configuration(self, kube_version):
        """Test the Lua configuration in nginx."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Verify Lua setup
        assert "lua_package_path" in nginx_conf
        assert "lua_shared_dict federation_auth_cache 10m;" in nginx_conf
        assert "content_by_lua_block {" in nginx_conf

    def test_prometheus_federation_auth_configmap_upstream_configuration(self, kube_version):
        """Test the upstream Prometheus backend configuration."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "ports": {"http": 9090},
            },
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Verify upstream configuration
        assert "upstream prometheus_backend {" in nginx_conf
        assert "keepalive 15;" in nginx_conf
        assert "9090" in nginx_conf  # Default Prometheus port
        assert ".prometheus" in nginx_conf or ".Release.Namespace" not in nginx_conf

    def test_prometheus_federation_auth_configmap_server_configuration(self, kube_version):
        """Test the server block configuration."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}, "authSidecar": {"port": 8080}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Verify server configuration
        assert "listen 8080;" in nginx_conf
        assert "server_tokens off;" in nginx_conf
        assert "server_name _;" in nginx_conf

    def test_prometheus_federation_auth_configmap_default_port(self, kube_version):
        """Test the default auth sidecar port."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Default port should be in the config
        # Extract the port from listen directive
        match = re.search(r"listen\s+(\d+);", nginx_conf)
        assert match is not None
        port = int(match.group(1))
        assert port > 0

    def test_prometheus_federation_auth_configmap_federate_endpoint(self, kube_version):
        """Test the /federate endpoint configuration."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Verify /federate location
        assert "location = /federate {" in nginx_conf
        assert "auth_request /auth;" in nginx_conf
        assert "proxy_pass http://prometheus_backend/federate;" in nginx_conf
        assert "proxy_read_timeout 300s;" in nginx_conf
        assert "proxy_connect_timeout 75s;" in nginx_conf
        assert 'proxy_set_header Authorization "";' in nginx_conf

    def test_prometheus_federation_auth_configmap_auth_endpoint(self, kube_version):
        """Test the /auth endpoint configuration."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Verify /auth location
        assert "location = /auth {" in nginx_conf
        assert "internal;" in nginx_conf
        assert "ngx.var.http_authorization" in nginx_conf
        assert 'os.getenv("REGISTRY_AUTH_TOKEN")' in nginx_conf
        assert "Missing Authorization header" in nginx_conf
        assert "Invalid Authorization format" in nginx_conf
        assert "Invalid federation token" in nginx_conf

    def test_prometheus_federation_auth_configmap_auth_token_validation(self, kube_version):
        """Test the auth token validation logic in Lua."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Verify token extraction patterns
        assert "Bearer" in nginx_conf  # Bearer token pattern
        assert "provided_token ~= registry_auth_token" in nginx_conf
        assert "ngx.status = 401" in nginx_conf
        assert "ngx.status = 403" in nginx_conf

    def test_prometheus_federation_auth_configmap_healthz_endpoint(self, kube_version):
        """Test the /healthz endpoint configuration."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Verify /healthz location
        assert "location /healthz {" in nginx_conf
        assert 'ngx.say("OK")' in nginx_conf
        assert "ngx.status = 200" in nginx_conf

    def test_prometheus_federation_auth_configmap_deny_all_default(self, kube_version):
        """Test that all paths are denied by default."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Verify default deny
        assert "location / {" in nginx_conf
        assert "deny all;" in nginx_conf

    def test_prometheus_federation_auth_configmap_proxy_headers(self, kube_version):
        """Test the proxy header configuration."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Verify proxy headers
        assert "proxy_set_header Host $host;" in nginx_conf
        assert "proxy_set_header X-Real-IP $remote_addr;" in nginx_conf
        assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in nginx_conf
        assert "proxy_set_header X-Forwarded-Proto $scheme;" in nginx_conf

    def test_prometheus_federation_auth_configmap_proxy_buffering(self, kube_version):
        """Test the proxy buffering configuration."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        # Verify buffering settings
        assert "proxy_buffering off;" in nginx_conf
        assert "proxy_buffer_size 4k;" in nginx_conf

    def test_prometheus_federation_auth_configmap_env_variables(self, kube_version):
        """Test that required environment variables are configured."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "data"}}},
            show_only=["charts/prometheus/templates/prometheus-federation-auth-configmap.yaml"],
        )

        assert len(docs) == 1
        nginx_conf = docs[0]["data"]["nginx.conf"]

        assert "env REGISTRY_AUTH_TOKEN;" in nginx_conf
