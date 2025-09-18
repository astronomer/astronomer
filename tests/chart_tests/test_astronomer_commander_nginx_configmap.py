import pytest

from tests import supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize(
    "kube_version",
    supported_k8s_versions,
)
class TestAstronomerCommanderNginxConfigMap:
    """Test class specifically for Commander nginx ConfigMap functionality."""

    @pytest.mark.parametrize(
        "plane_mode,auth_sidecar_enabled,should_render_configmap",
        [
            ("data", True, True),
            ("data", False, False),
            ("unified", True, False),
            ("unified", False, False),
            ("control", True, False),
            ("control", False, False),
        ],
    )
    def test_conditional_rendering(self, kube_version, plane_mode, auth_sidecar_enabled, should_render_configmap):
        """Test that nginx ConfigMap is only rendered when auth-sidecar is enabled in data plane mode."""
        values = {
            "global": {
                "plane": {"mode": plane_mode},
            },
        }

        if auth_sidecar_enabled:
            values["global"]["authSidecar"] = {"enabled": True}

        docs = render_chart(
            kube_version=kube_version,
            values=values,
            show_only=["charts/astronomer/templates/commander/commander-nginx-configmap.yaml"],
        )

        if should_render_configmap:
            assert len(docs) == 1
            doc = docs[0]
            assert doc["kind"] == "ConfigMap"
            assert doc["metadata"]["name"] == "release-name-commander-nginx-conf"
        else:
            assert len(docs) == 0

    def test_openshift_compatibility(self, kube_version):
        """Test that nginx ConfigMap contains proper OpenShift-compatible configuration."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}, "authSidecar": {"enabled": True}},
            },
            show_only=["charts/astronomer/templates/commander/commander-nginx-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        nginx_conf = doc["data"]["nginx.conf"]

        assert "pid /tmp/nginx.pid;" in nginx_conf
        assert "client_body_temp_path /tmp/client_temp;" in nginx_conf
        assert "proxy_temp_path       /tmp/proxy_temp_path;" in nginx_conf
        assert "fastcgi_temp_path     /tmp/fastcgi_temp;" in nginx_conf
        assert "uwsgi_temp_path       /tmp/uwsgi_temp;" in nginx_conf
        assert "scgi_temp_path        /tmp/scgi_temp;" in nginx_conf

        assert "listen 8080;" in nginx_conf
        assert "listen 9090 http2;" in nginx_conf

    def test_upstream_configuration(self, kube_version):
        """Test that nginx ConfigMap contains correct upstream configurations."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}, "authSidecar": {"enabled": True}},
            },
            show_only=["charts/astronomer/templates/commander/commander-nginx-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        nginx_conf = doc["data"]["nginx.conf"]

        assert "upstream commander-http {" in nginx_conf
        assert "server 127.0.0.1:8880;" in nginx_conf
        assert "upstream commander-grpc {" in nginx_conf
        assert "server 127.0.0.1:50051;" in nginx_conf

    def test_location_blocks(self, kube_version):
        """Test that nginx ConfigMap contains proper location blocks for HTTP and GRPC."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}, "authSidecar": {"enabled": True}},
            },
            show_only=["charts/astronomer/templates/commander/commander-nginx-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        nginx_conf = doc["data"]["nginx.conf"]

        assert "location /nginx-health {" in nginx_conf
        assert 'return 200 "healthy\\n";' in nginx_conf
        assert "location /metadata {" in nginx_conf
        assert "proxy_pass http://commander-http;" in nginx_conf

        assert "location / {" in nginx_conf
        assert "grpc_pass grpc://commander-grpc;" in nginx_conf

    def test_proxy_headers(self, kube_version):
        """Test that nginx ConfigMap includes proper proxy headers."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}, "authSidecar": {"enabled": True}},
            },
            show_only=["charts/astronomer/templates/commander/commander-nginx-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        nginx_conf = doc["data"]["nginx.conf"]

        # Test HTTP proxy headers
        assert "proxy_set_header Host $host;" in nginx_conf
        assert "proxy_set_header X-Real-IP $remote_addr;" in nginx_conf
        assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in nginx_conf
        assert "proxy_set_header X-Forwarded-Proto $scheme;" in nginx_conf

        # Test GRPC headers
        assert "grpc_set_header Host $host;" in nginx_conf
        assert "grpc_set_header X-Real-IP $remote_addr;" in nginx_conf
        assert "grpc_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in nginx_conf
        assert "grpc_set_header X-Forwarded-Proto $scheme;" in nginx_conf

    def test_timeout_and_buffer_settings(self, kube_version):
        """Test that nginx ConfigMap includes proper timeout and buffer configurations."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}, "authSidecar": {"enabled": True}},
            },
            show_only=["charts/astronomer/templates/commander/commander-nginx-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]
        nginx_conf = doc["data"]["nginx.conf"]

        # Test HTTP proxy timeouts and buffers
        assert "proxy_buffer_size 16k;" in nginx_conf
        assert "proxy_buffers 4 16k;" in nginx_conf
        assert "proxy_busy_buffers_size 16k;" in nginx_conf
        assert "proxy_connect_timeout 30s;" in nginx_conf
        assert "proxy_send_timeout 30s;" in nginx_conf
        assert "proxy_read_timeout 30s;" in nginx_conf

        # Test GRPC timeouts and buffers
        assert "grpc_read_timeout 300s;" in nginx_conf
        assert "grpc_send_timeout 300s;" in nginx_conf
        assert "client_body_timeout 300s;" in nginx_conf
        assert "grpc_buffer_size 16k;" in nginx_conf

    def test_metadata_and_labels(self, kube_version):
        """Test that nginx ConfigMap has correct metadata and labels."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}, "authSidecar": {"enabled": True}},
            },
            show_only=["charts/astronomer/templates/commander/commander-nginx-configmap.yaml"],
        )

        assert len(docs) == 1
        doc = docs[0]

        assert doc["apiVersion"] == "v1"
        assert doc["kind"] == "ConfigMap"
        assert doc["metadata"]["name"] == "release-name-commander-nginx-conf"

        expected_labels = {
            "component": "commander-nginx-conf",
            "tier": "astronomer",
            "release": "release-name",
            "heritage": "Helm",
            "plane": "data",
        }
        for key, value in expected_labels.items():
            assert doc["metadata"]["labels"][key] == value
