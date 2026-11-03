"""Verifies the platform installs and runs on a real OpenShift API server.

test_profile.yaml sets cluster_provider: openshift, so the cluster is MicroShift rather than
KIND and these tests only read the result of that install.

What KIND cannot tell us: SecurityContextConstraints do not exist there, so nothing checks that
the platform's pods still fit OpenShift's restricted profile -- and a pod admitted by the wrong
SCC is Running like any other, so helm-install.py's pod-phase wait never notices.
"""

import pytest
from kubernetes import client, config

from tests.utils.k8s import KUBECONFIG_UNIFIED, find_admission_rejection_events

NAMESPACE = "astronomer"

# Written onto the pod at admission, so its presence proves SCC admission ran and its value says
# which constraint was used.
SCC_ANNOTATION = "openshift.io/scc"

# Both names, because which is the default is a property of the cluster's OpenShift version:
# restricted-v2 on anything current, restricted on older ones.
RESTRICTED_SCCS = frozenset({"restricted-v2", "restricted"})


@pytest.fixture(scope="module")
def core_client() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def platform_pods(core_client) -> list:
    """Live pods in the platform namespace; one mid-deletion is from a revision on its way out."""
    pods = [pod for pod in core_client.list_namespaced_pod(NAMESPACE).items if pod.metadata.deletion_timestamp is None]
    assert pods, f"No pods at all in the {NAMESPACE} namespace -- the chart install cannot have succeeded"
    return pods


def test_no_admission_rejection_events(core_client):
    """Nothing was refused admission while the chart installed.

    A rejected pod is never created, so it leaves no unhealthy Pod object -- only a FailedCreate
    Warning on whatever tried. Empty name prefix: every one in the namespace matters here.
    """
    rejections = find_admission_rejection_events(core_client, NAMESPACE, "")
    assert not rejections, "Admission refused at least one platform pod:\n" + "\n".join(f"  {line}" for line in rejections)


def test_every_pod_runs_under_a_restricted_scc(platform_pods):
    """Every platform pod was admitted under a built-in restricted SCC.

    The platform's pods satisfy restricted-v2 as they are, and with global.openshift.enabled as
    the whole configuration that is all they get. A pod spec that gains a hostPath, a fixed uid
    or a privileged container has to be fixed in the spec, and this is what notices.

    Read from the pod, not from the SCC objects: what matters is which constraint OpenShift chose.
    """
    elevated = {
        pod.metadata.name: (pod.metadata.annotations or {}).get(SCC_ANNOTATION)
        for pod in platform_pods
        if (pod.metadata.annotations or {}).get(SCC_ANNOTATION) not in RESTRICTED_SCCS
    }
    assert not elevated, (
        f"These pods were not admitted by one of {sorted(RESTRICTED_SCCS)} (pod: {SCC_ANNOTATION}). "
        "None means SCC admission never saw the pod -- is this really an OpenShift cluster? Any "
        f"other name means it needs an elevated SCC: {elevated}"
    )


def test_bundled_nginx_is_not_deployed(core_client):
    """The chart's own ingress controller is off, leaving the cluster's router to front the platform.

    Left on, it would also fight openshift-ingress for host ports 80/443.
    """
    nginx_pods = sorted(
        pod.metadata.name
        for pod in core_client.list_namespaced_pod(NAMESPACE, label_selector="component=cp-ingress-controller").items
    )
    assert not nginx_pods, (
        "global.nginx.enabled should be false on OpenShift (configs/openshift.yaml), but the bundled "
        f"ingress controller is running: {', '.join(nginx_pods)}"
    )
