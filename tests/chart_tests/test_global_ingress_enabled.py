from pathlib import Path

import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils.chart import render_chart


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
class TestGlobalIngressEnabled:
    def test_all_ingress_suppressed_when_disabled(self, kube_version):
        """global.ingress.enabled=false renders no platform ingress."""
        all_ingress_files = [str(x.relative_to(git_root_dir)) for x in Path(git_root_dir).rglob("*ingress*.yaml")]
        always_rendered_ingress = [f for f in all_ingress_files if "external-es-proxy-ingress.yaml" not in f]

        docs = render_chart(
            kube_version=kube_version,
            values={"global": {"ingress": {"enabled": False}}},
            show_only=sorted(always_rendered_ingress),
        )
        assert not docs

    def test_external_es_proxy_ingress_suppressed_when_disabled(self, kube_version):
        """The data-plane external-es-proxy ingress is also gated by global.ingress.enabled."""
        docs = render_chart(
            kube_version=kube_version,
            values={
                "global": {
                    "ingress": {"enabled": False},
                    "plane": {"mode": "data"},
                    "customLogging": {"enabled": True},
                },
                "astronomer": {"ingress": {"enabled": True}},
            },
            show_only=["charts/external-es-proxy/templates/external-es-proxy-ingress.yaml"],
        )
        assert not docs

    def test_ingress_enabled_by_default(self, kube_version):
        """Default values (flag absent) still render the platform ingress — no-op upgrade."""
        all_ingress_files = [str(x.relative_to(git_root_dir)) for x in Path(git_root_dir).rglob("*ingress*.yaml")]
        always_rendered_ingress = [f for f in all_ingress_files if "external-es-proxy-ingress.yaml" not in f]

        docs = render_chart(
            kube_version=kube_version,
            show_only=sorted(always_rendered_ingress),
        )
        assert docs
        for doc in docs:
            assert doc["kind"] == "Ingress"
