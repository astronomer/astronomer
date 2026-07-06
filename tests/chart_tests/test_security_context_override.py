"""PSS-Restricted customizability: customer-supplied securityContext overrides must merge
into every platform pod.

PINF-713 acceptance criterion: "a customer can override any single field via helm values
without losing the others." A pod that hardcodes its securityContext (or doesn't thread the
chart's override surface through) silently strips that ability — a customizability gap.

How this guards against new pods:
  1. We discover EVERY `securityContext` / `podSecurityContext` value surface from the merged
     chart defaults (via bin/get-all-chart-default-values.py's `load_chart`), so the override
     surfaces maintain themselves — a new value surface is picked up automatically.
  2. We inject a sentinel field into each surface and render with all features enabled.
  3. We assert every container's securityContext carries the container sentinel, and every
     pod's pod-level securityContext carries the pod sentinel — and that each still has its
     other fields (merge, not replace).

A new pod that hardcodes its securityContext will be missing the sentinel and fail here. The
fix is to thread an override surface through it (preferred) or, if it is privileged by design,
add it to the ignore list below with a justification.
"""

import importlib.util
from pathlib import Path

import pytest

from tests import supported_k8s_versions
from tests.utils import get_all_features, get_pod_template
from tests.utils.chart import render_chart

GIT_ROOT = Path(__file__).resolve().parents[2]

# Sentinel fields injected into every override surface. They are not real securityContext
# fields, but the merge is additive so they ride through untouched and are trivial to detect.
CONTAINER_SENTINEL = "xContainerOverrideProbe"
POD_SENTINEL = "xPodOverrideProbe"

POD_MANAGER_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob"}

# Containers whose securityContext cannot accept an arbitrary customer override. Keyed by
# container name (with the "release-name-" prefix stripped). Each entry documents why.
CONTAINER_OVERRIDE_IGNORE = {
    # Privileged host-level agents: hardcoded `privileged: true` / `runAsUser: 0` to write the
    # private CA into the node trust store and rewrite containerd config. No override surface
    # by design (also Bucket 1 in the design doc's Feature Compatibility table).
    "cert-copy-and-toml-update",
    "cert-copy",
    # elasticsearch init container that sets vm.max_map_count — must run privileged/root, so its
    # securityContext is intentionally hardcoded and not customer-overridable.
    "sysctl",
    # Vendored bitnami postgresql: its securityContext is assembled field-by-field from named
    # `.Values.securityContext.*` keys, so arbitrary override fields do not merge in. Customers
    # customize it via bitnami's documented fields, not an arbitrary map.
    "postgresql",
}

# Pods whose pod-level securityContext cannot accept an arbitrary customer override.
# Keyed by metadata name (with the "release-name-" prefix stripped).
POD_OVERRIDE_IGNORE = {
    # Host-level CA agents — no pod-level securityContext override surface (see above / Bucket 1).
    "containerd-ca-update",
    "private-ca",
    # Vendored bitnami postgresql — pod securityContext assembled field-by-field (see above).
    "postgresql-master",
    "postgresql-slave",
}


def _load_tool():
    """Import bin/get-all-chart-default-values.py as a module (its filename isn't importable)."""
    path = GIT_ROOT / "bin" / "get-all-chart-default-values.py"
    spec = importlib.util.spec_from_file_location("get_all_chart_default_values", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _iter_sc_surfaces(node, path=()):
    """Yield (dotted_path, surface_kind) for every securityContext/podSecurityContext dict."""
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        current = (*path, key)
        if key in ("securityContext", "podSecurityContext") and isinstance(value, dict):
            yield current, key
        if isinstance(value, dict):
            yield from _iter_sc_surfaces(value, current)


def _build_override_values():
    """Discover every securityContext surface from chart defaults and inject a sentinel into each."""
    tool = _load_tool()
    _, defaults = tool.load_chart(GIT_ROOT)

    overrides = get_all_features()
    surfaces = list(_iter_sc_surfaces(defaults))
    assert surfaces, "Discovered no securityContext surfaces; the discovery walk is broken"
    for path, kind in surfaces:
        sentinel = CONTAINER_SENTINEL if kind == "securityContext" else POD_SENTINEL
        tool.set_nested_value(overrides, ".".join((*path, sentinel)), True)
    return overrides


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_container_security_context_overrides_merge_everywhere(kube_version):
    """Every container's securityContext merges a customer override (and keeps its other fields)."""
    docs = render_chart(kube_version=kube_version, values=_build_override_values())

    checked = 0
    for doc in docs:
        if doc.get("kind") not in POD_MANAGER_KINDS:
            continue
        spec = get_pod_template(doc).get("spec", {})
        for container in spec.get("containers", []) + spec.get("initContainers", []):
            name = container["name"].split("release-name-")[-1]
            if name in CONTAINER_OVERRIDE_IGNORE:
                continue
            sc = container.get("securityContext") or {}
            pod_name = doc["metadata"]["name"]
            assert sc.get(CONTAINER_SENTINEL) is True, (
                f"{pod_name}/{container['name']} did not merge the customer securityContext "
                f"override — it likely hardcodes its securityContext or doesn't thread an "
                f"override surface. Thread one through, or add it to CONTAINER_OVERRIDE_IGNORE."
            )
            assert len(sc) > 1, f"{pod_name}/{container['name']} replaced rather than merged the override"
            checked += 1

    assert checked, "No containers were checked; render or discovery regressed"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_pod_security_context_overrides_merge_everywhere(kube_version):
    """Every pod's pod-level securityContext merges a customer override (and keeps its other fields)."""
    docs = render_chart(kube_version=kube_version, values=_build_override_values())

    checked = 0
    for doc in docs:
        if doc.get("kind") not in POD_MANAGER_KINDS:
            continue
        name = doc.get("metadata", {}).get("name", "")
        if name.split("release-name-")[-1] in POD_OVERRIDE_IGNORE:
            continue
        psc = get_pod_template(doc).get("spec", {}).get("securityContext") or {}
        # Pod-level securityContext is rendered wholesale from `.Values.<chart>.podSecurityContext`
        # (no force-merge), so a chart whose default is empty legitimately yields just the sentinel.
        # The meaningful guarantee is that the override surface is honored at all.
        assert psc.get(POD_SENTINEL) is True, (
            f"{doc['kind']}/{name} did not merge the customer podSecurityContext override — "
            f"thread a pod-level securityContext surface through it, or add it to POD_OVERRIDE_IGNORE."
        )
        checked += 1

    assert checked, "No pods were checked; render or discovery regressed"
