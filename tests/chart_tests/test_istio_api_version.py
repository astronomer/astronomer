"""Cross-cutting guard: every Istio networking object the chart renders is networking.istio.io/v1.

The Istio networking group graduated to v1 in Istio 1.22, and the v1alpha3 aliases are removed in
Istio 1.28. A single object left on an older alias is not a local problem: the API server rejects
it outright once the cluster drops that version, failing the whole install.

Coverage here is deliberately in two halves, because neither alone covers *every* object:

- test_rendered_istio_objects_use_v1 renders the whole chart with Istio enabled and checks the
  apiVersion of each Istio object that comes out. It proves what `apiVersion.istio.networking`
  actually resolves to, but only for templates that render under those values.
- test_istio_templates_use_the_apiversion_helper scans the templates instead, so a template gated
  on values no test happens to set still cannot hardcode an apiVersion of its own.

Together: every Istio networking object comes from the one helper, and that helper renders v1.

Kinds are limited to the networking.istio.io kinds that have a v1 — EnvoyFilter (v1alpha3 only)
and ProxyConfig (v1beta1 only) have no v1 to move to, and the chart renders neither. Adding one
later means adding it to a separate expectation, not to ISTIO_V1_KINDS.
"""

import re

import pytest

from tests import git_root_dir, supported_k8s_versions
from tests.utils.chart import render_chart

ISTIO_API_VERSION = "networking.istio.io/v1"
ISTIO_GROUP = "networking.istio.io/"

# networking.istio.io kinds that are served at v1.
ISTIO_V1_KINDS = frozenset(
    {
        "DestinationRule",
        "Gateway",
        "ServiceEntry",
        "Sidecar",
        "VirtualService",
        "WorkloadEntry",
        "WorkloadGroup",
    }
)

APIVERSION_HELPER = 'template "apiVersion.istio.networking"'

# `kind: Gateway` also names a cert-manager/gateway-api kind, so the scan below keys on the helper
# count matching the kind count rather than assuming any one kind belongs to Istio.
ISTIO_KIND_RE = re.compile(rf"^kind: ({'|'.join(sorted(ISTIO_V1_KINDS))})\s*$", re.MULTILINE)
# Any literal networking.istio.io apiVersion, e.g. networking.istio.io/v1alpha3. The RBAC rules
# that grant VirtualService access name the bare group with no version, so they do not match.
ISTIO_LITERAL_APIVERSION_RE = re.compile(r"networking\.istio\.io/v\S*")

GATEWAY = "istio-system/default-gateway"


def _istio_templates():
    """Return every chart template that declares an Istio networking object, repo-relative."""
    template_dirs = [git_root_dir / "charts", git_root_dir / "templates"]
    return sorted(
        path.relative_to(git_root_dir).as_posix()
        for template_dir in template_dirs
        for path in template_dir.rglob("*.yaml")
        if ISTIO_KIND_RE.search(path.read_text())
    )


ISTIO_TEMPLATES = _istio_templates()


def _istio_values(plane_mode):
    """Turn on everything that gates an Istio object: the sidecars, the gateway and its routes.

    global.authSidecar.enabled is mandatory alongside the gateway — without it the render aborts,
    see tests/chart_tests/test_istio_virtualservice.py. A data plane additionally needs
    plane.domainPrefix, or its prometheus VirtualService is suppressed.
    """
    plane = {"mode": plane_mode}
    if plane_mode == "data":
        plane["domainPrefix"] = "dp"
    return {
        "global": {
            "istio": {"enabled": True, "gateway": {"enabled": True, "name": GATEWAY}},
            "nginx": {"enabled": False},
            "authSidecar": {"enabled": True},
            "plane": plane,
        }
    }


def test_istio_templates_are_found():
    """The template scan below is only a guard while it still finds the Istio templates.

    A rename or a reformat that stops ISTIO_KIND_RE matching would otherwise turn
    test_istio_templates_use_the_apiversion_helper into a test over an empty list, which passes.
    """
    assert ISTIO_TEMPLATES


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
@pytest.mark.parametrize("plane_mode", ["unified", "control", "data"])
def test_rendered_istio_objects_use_v1(kube_version, plane_mode):
    """Every Istio object in a full Istio-enabled render is networking.istio.io/v1.

    All three plane modes are rendered because the object set differs per mode: the commander and
    prometheus-federate VirtualServices are data-plane only, while the customer-facing ones are
    control-plane only.
    """
    docs = render_chart(kube_version=kube_version, values=_istio_values(plane_mode))
    istio_docs = [doc for doc in docs if doc.get("apiVersion", "").startswith(ISTIO_GROUP)]
    # A list rather than a name-keyed dict: the two default-sidecar-config Sidecars differ only by
    # namespace (one in global.istio.rootNamespace, one in the release namespace), so keying on the
    # name alone would collapse them and could hide a wrong apiVersion on one of the pair.
    inventory = sorted(
        (doc["kind"], doc["metadata"].get("namespace", "(release)"), doc["metadata"]["name"], doc["apiVersion"])
        for doc in istio_docs
    )

    # A passing assertion prints nothing, so the apiVersion each object actually rendered at is only
    # visible if the test says so: `pytest --capture=no` turns this into a readable inventory.
    for kind, namespace, name, api_version in inventory:
        print(f"{plane_mode:8} k8s {kube_version:8} {api_version:34} {kind:15} {namespace:14} {name}")

    # The Sidecars are unconditional under global.istio.enabled, so every mode renders some.
    assert istio_docs, f"no Istio objects rendered in {plane_mode} mode"
    assert ISTIO_V1_KINDS.issuperset({kind for kind, *_ in inventory})
    wrong_version = [entry for entry in inventory if entry[-1] != ISTIO_API_VERSION]
    assert not wrong_version, f"expected every Istio object at {ISTIO_API_VERSION}, got {wrong_version}"


@pytest.mark.parametrize("template", ISTIO_TEMPLATES)
def test_istio_templates_use_the_apiversion_helper(template):
    """Each Istio object in a template takes its apiVersion from apiVersion.istio.networking.

    One helper for the whole chart is what makes the next group bump a one-line change, and keeps a
    template that renders only under values no test sets from drifting to an older alias unnoticed.
    """
    contents = (git_root_dir / template).read_text()
    assert not ISTIO_LITERAL_APIVERSION_RE.findall(contents), f"{template} hardcodes an Istio apiVersion"
    assert contents.count(APIVERSION_HELPER) == len(ISTIO_KIND_RE.findall(contents))
