"""Tests for the MCP server component (APC-1767): Deployment, Service, Ingress, and the
BYO-ingress fail-closed guard (APC-1768).

UNVERIFIED: written without helm or a Go toolchain available in the authoring environment
(see internal/houston/client.go's doc comment in apc-mcp-server for the broader context).
These tests have not actually been run against `helm template` here — review and run
locally (`make test-unit` in this repo) before merging. Modeled directly on
test_astronomer_navigator.py (render_chart/show_only pattern) and
test_auth_flow_global_base_domain.py (the pytest.raises(CalledProcessError) pattern for a
render that must fail).
"""

from subprocess import CalledProcessError

import pytest

from tests import supported_k8s_versions
from tests.utils import get_containers_by_name, get_env_vars_dict
from tests.utils.chart import render_chart

DEPLOYMENT = "charts/astronomer/templates/mcp-server/mcp-server-deployment.yaml"
SERVICE = "charts/astronomer/templates/mcp-server/mcp-server-service.yaml"
INGRESS = "charts/astronomer/templates/mcp-server/mcp-server-ingress.yaml"
SERVICEACCOUNT = "charts/astronomer/templates/mcp-server/mcp-server-serviceaccount.yaml"

BASE_DOMAIN = "example.com"
GLOBAL_BASE_DOMAIN = "astro.example.com"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestMcpServerDeployment:
    @pytest.mark.parametrize(
        "plane_mode,expected_count",
        [
            ("control", 1),
            ("unified", 1),
            ("data", 0),
        ],
    )
    def test_deployment_plane_mode(self, kube_version, plane_mode, expected_count):
        """The MCP server is control-plane / unified only, unlike registry (data/unified)."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": plane_mode}},
                "astronomer": {"mcpServer": {"enabled": True}},
            },
            show_only=[DEPLOYMENT],
        )
        assert len(docs) == expected_count
        if expected_count:
            assert docs[0]["kind"] == "Deployment"

    def test_deployment_disabled_by_default(self, kube_version):
        """mcpServer.enabled defaults to false -- an existing control-plane install must not
        suddenly grow this component on an unrelated chart upgrade."""
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=[DEPLOYMENT],
        )
        assert len(docs) == 0

    def test_deployment_default_values(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"mcpServer": {"enabled": True}},
            },
            show_only=[DEPLOYMENT],
        )
        assert len(docs) == 1
        doc = docs[0]
        assert doc["spec"]["replicas"] == 2

        c_by_name = get_containers_by_name(doc)
        assert "mcp-server" in c_by_name
        container = c_by_name["mcp-server"]
        assert "ap-mcp-server" in container["image"]
        assert container["securityContext"]["readOnlyRootFilesystem"] is True

    def test_deployment_env_vars(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"mcpServer": {"enabled": True}},
            },
            show_only=[DEPLOYMENT],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["mcp-server"]["env"])

        assert env_vars["LISTEN_ADDR"] == ":8080"
        assert env_vars["HOUSTON_API_URL"] == "http://release-name-houston.default.svc.cluster.local:8871/v1"
        assert env_vars["MCP_ENABLED_GROUPS"] == "platform_read,platform_write"

    def test_deployment_enabled_groups_customizable(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"mcpServer": {"enabled": True, "enabledGroups": ["platform_read"]}},
            },
            show_only=[DEPLOYMENT],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["mcp-server"]["env"])
        assert env_vars["MCP_ENABLED_GROUPS"] == "platform_read"

    def test_deployment_replicas(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"mcpServer": {"enabled": True, "replicas": 5}},
            },
            show_only=[DEPLOYMENT],
        )
        assert len(docs) == 1
        assert docs[0]["spec"]["replicas"] == 5

    def test_deployment_user_provided_env_and_secret_vars(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {
                    "mcpServer": {
                        "enabled": True,
                        "env": [{"name": "MY_CUSTOM_VAR", "value": "custom-value"}],
                        "secret": [{"envName": "MY_SECRET_VAR", "secretName": "my-secret", "secretKey": "my-key"}],
                    }
                },
            },
            show_only=[DEPLOYMENT],
        )
        assert len(docs) == 1
        c_by_name = get_containers_by_name(docs[0])
        env_vars = get_env_vars_dict(c_by_name["mcp-server"]["env"])
        assert env_vars["MY_CUSTOM_VAR"] == "custom-value"
        assert env_vars["MY_SECRET_VAR"] == {"secretKeyRef": {"name": "my-secret", "key": "my-key"}}


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestMcpServerService:
    def test_service_renders_when_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"mcpServer": {"enabled": True}},
            },
            show_only=[SERVICE],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "Service"
        assert docs[0]["spec"]["ports"][0]["port"] == 8080

    def test_service_absent_when_disabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=[SERVICE],
        )
        assert len(docs) == 0

    def test_service_absent_on_data_plane(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "data"}},
                "astronomer": {"mcpServer": {"enabled": True}},
            },
            show_only=[SERVICE],
        )
        assert len(docs) == 0


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestMcpServerServiceAccount:
    def test_serviceaccount_renders_when_enabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {"plane": {"mode": "control"}},
                "astronomer": {"mcpServer": {"enabled": True}},
            },
            show_only=[SERVICEACCOUNT],
        )
        assert len(docs) == 1
        assert docs[0]["kind"] == "ServiceAccount"

    def test_serviceaccount_absent_when_disabled(self, kube_version):
        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"plane": {"mode": "control"}}},
            show_only=[SERVICEACCOUNT],
        )
        assert len(docs) == 0


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestMcpServerIngress:
    def _values(self, plane_mode="control", *, ha=False, auth_sidecar=False, enabled=True):
        cpha = {}
        if ha:
            cpha = {"enabled": True, "globalBaseDomain": GLOBAL_BASE_DOMAIN}
        global_values = {
            "plane": {"mode": plane_mode},
            "baseDomain": BASE_DOMAIN,
            "authSidecar": {"enabled": auth_sidecar},
        }
        if cpha:
            global_values["controlPlaneHA"] = cpha
        return {"global": global_values, "astronomer": {"mcpServer": {"enabled": enabled}}}

    def test_ingress_renders_with_auth_annotations(self, kube_version):
        docs = render_chart(kube_version=kube_version, values=self._values(), show_only=[INGRESS])
        assert len(docs) == 1
        annotations = docs[0]["metadata"]["annotations"]
        assert annotations["nginx.ingress.kubernetes.io/auth-url"] == (
            "http://release-name-houston.default.svc.cluster.local:8871/v1/authorization/agent"
        )
        assert "nginx.ingress.kubernetes.io/auth-signin" in annotations
        assert "nginx.ingress.kubernetes.io/auth-response-headers" in annotations
        assert docs[0]["spec"]["rules"][0]["host"] == f"mcp-server.{BASE_DOMAIN}"

    def test_ingress_absent_when_disabled(self, kube_version):
        docs = render_chart(kube_version=kube_version, values=self._values(enabled=False), show_only=[INGRESS])
        assert len(docs) == 0

    def test_ingress_absent_on_data_plane(self, kube_version):
        docs = render_chart(kube_version=kube_version, values=self._values(plane_mode="data"), show_only=[INGRESS])
        assert len(docs) == 0

    def test_ingress_cp_ha_adds_global_host(self, kube_version):
        docs = render_chart(kube_version=kube_version, values=self._values(ha=True), show_only=[INGRESS])
        assert len(docs) == 1
        hosts = [r["host"] for r in docs[0]["spec"]["rules"]]
        assert hosts == [f"mcp-server.{BASE_DOMAIN}", f"mcp-server.{GLOBAL_BASE_DOMAIN}"]

    def test_ingress_fails_closed_under_byo_ingress(self, kube_version):
        """APC-1768: mcpServer.enabled + global.authSidecar.enabled must fail the render
        rather than silently produce an ingress with no auth-url annotation."""
        with pytest.raises(CalledProcessError) as excinfo:
            render_chart(kube_version=kube_version, values=self._values(auth_sidecar=True), show_only=[INGRESS])
        assert "APC-1768" in excinfo.value.stderr.decode("utf-8")

    def test_byo_ingress_without_mcp_server_is_unaffected(self, kube_version):
        """The guard above must only fire when mcpServer is explicitly enabled -- an existing
        BYO-ingress install that has not opted into the MCP server must render exactly as it
        did before this component existed."""
        docs = render_chart(
            kube_version=kube_version,
            values=self._values(auth_sidecar=True, enabled=False),
            show_only=[INGRESS],
        )
        assert len(docs) == 0
