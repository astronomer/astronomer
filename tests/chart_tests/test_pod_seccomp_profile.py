"""PSS-Restricted conformance: every platform pod must set a seccomp profile.

The Pod Security Standards "Restricted" profile requires `seccompProfile.type` to be
`RuntimeDefault` (or `Localhost`) at the pod level or on every container — absence is a
violation. Platform pods deliver this via the pod-level `astronomer.podSecurityContext`
helper (`.Values.podSecurityContext.seccompProfile`).

This is a cross-cutting regression guard: any newly added platform pod manager that forgets
the pod-level seccomp profile will fail here. See also test_non_root_user.py (container-level
runAsNonRoot), the sibling control.
"""

import pytest

from tests import supported_k8s_versions
from tests.utils import get_all_features, get_pod_template
from tests.utils.chart import render_chart

# Pods that do not yet set a pod-level seccomp profile. These are outside the scope of the
# astronomer platform-chart hardening (PINF-713) and are tracked separately; keep this list
# tight and remove entries as each component becomes PSS-Restricted conformant.
# Keyed by metadata name with the "release-name-" prefix stripped.
SECCOMP_IGNORE_LIST = {
    "elasticsearch-curator",  # elasticsearch sub-chart
    "containerd-ca-update",  # private-ca daemonset
    "private-ca",  # private-ca daemonset
    "vector",  # logging daemonset (also runs as root; see test_non_root_user.py)
    "jetstream-job",  # nats jetstream bootstrap job
}

POD_MANAGER_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob"}


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_all_platform_pods_set_seccomp_profile(kube_version):
    """Every platform pod manager renders pod-level seccompProfile.type: RuntimeDefault."""
    docs = render_chart(kube_version=kube_version, values=get_all_features())

    checked = []
    for doc in docs:
        if doc.get("kind") not in POD_MANAGER_KINDS:
            continue
        name = doc.get("metadata", {}).get("name", "")
        if name.split("release-name-")[-1] in SECCOMP_IGNORE_LIST:
            continue
        pod_spec = get_pod_template(doc).get("spec", {})
        seccomp = (pod_spec.get("securityContext") or {}).get("seccompProfile") or {}
        assert seccomp.get("type") == "RuntimeDefault", (
            f"{doc['kind']}/{name} is missing pod-level seccompProfile.type: RuntimeDefault"
        )
        checked.append(name)

    # Guard against the render returning no pod managers (e.g. a helper/filter regression),
    # which would make the assertions above vacuously pass.
    assert checked, "No platform pod managers were rendered; cannot validate seccomp profiles"


@pytest.mark.parametrize("kube_version", supported_k8s_versions)
def test_data_plane_jwks_hook_job_sets_seccomp_profile(kube_version):
    """The commander JWKS hook Job renders only in data-plane mode, so it is not covered by
    the all-features (unified) render above. Verify it carries the seccomp profile too."""
    docs = render_chart(
        kube_version=kube_version,
        values={"global": {"plane": {"mode": "data"}}},
        show_only=["charts/astronomer/templates/commander/jwks-hooks/commander-jwks-hooks.yaml"],
    )
    assert len(docs) == 1
    assert docs[0]["kind"] == "Job"
    pod_spec = get_pod_template(docs[0]).get("spec", {})
    seccomp = (pod_spec.get("securityContext") or {}).get("seccompProfile") or {}
    assert seccomp.get("type") == "RuntimeDefault"
