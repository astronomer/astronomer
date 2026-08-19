import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils.chart import render_chart

# Discover every ingress template at collection time so a newly added ingress is
# automatically covered — no hardcoded list to keep in sync.
INGRESS_TEMPLATES = sorted(
    str(p.relative_to(git_root_dir)) for p in git_root_dir.glob("charts/**/*ingress*.yaml")
)

# Some ingresses belong to sub-charts gated by a Chart.yaml condition, so their template
# isn't compiled under default values and helm cannot --show-only it. Give those the
# minimal values that make the sub-chart compile (and render), so the gate is what we test.
COMPILE_VALUES = {
    "charts/external-es-proxy/templates/external-es-proxy-ingress.yaml": {
        "global": {"plane": {"mode": "data"}, "customLogging": {"enabled": True}},
        "astronomer": {"ingress": {"enabled": True}},
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in base.items()}
    for k, v in override.items():
        out[k] = _merge(out.get(k, {}), v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def test_ingress_templates_discovered():
    # Guard against a broken glob silently parametrizing zero templates.
    assert INGRESS_TEMPLATES, "no ingress templates found — check the discovery glob"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
@pytest.mark.parametrize("template", INGRESS_TEMPLATES)
class TestGlobalIngressEnabled:
    def test_suppressed_when_disabled(self, template, kube_version):
        values = _merge(COMPILE_VALUES.get(template, {}), {"global": {"ingress": {"enabled": False}}})
        docs = render_chart(kube_version=kube_version, values=values, show_only=[template])
        assert not docs

    def test_default_matches_enabled(self, template, kube_version):
        # The gate is a no-op when on: flag-absent output == flag-true output, for every
        # template. Don't assert a doc count — many templates render nothing by default
        # (gated by baseDomain / plane.mode / perHostIngress).
        base = COMPILE_VALUES.get(template, {})
        default = render_chart(kube_version=kube_version, values=base, show_only=[template])
        enabled = render_chart(
            kube_version=kube_version,
            values=_merge(base, {"global": {"ingress": {"enabled": True}}}),
            show_only=[template],
        )
        assert default == enabled
