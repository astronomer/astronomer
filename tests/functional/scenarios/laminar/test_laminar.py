"""Verifies Kyverno evaluated Laminar's api-server and hypervisor pods, and that every
policy result passed.

Ordering is the scenario: test_profile.yaml installs Kyverno from pre_helm_scripts, the only
window between the cluster existing and `helm install`, so the pods the chart creates pass
through admission on their way in. helm-install.py labels the namespace before installing, so
the `platform: astronomer` label every policy selects on is already there.

The scan is audit-only -- bin/install-kyverno-scan.py force-overrides every policy to Audit
(PINF-1034) -- so Kyverno cannot refuse a pod and a failing install is not the signal. What
remains is that the policies produced results for these pods and none of them failed.

Laminar's own health is not asserted here: bin/helm-install.py's wait_for_healthy_pods already
gates the install, and this file deliberately checks only the Kyverno relationship. Note that
wait checks pod phase, which stays Running through a CrashLoopBackOff.

Module-scoped clients built directly from KUBECONFIG_UNIFIED rather than conftest.py's
function-scoped fixtures, the same pattern as auth-sidecar and custom-image-sha."""

import pytest
from kubernetes import client, config

from tests.utils.k8s import KUBECONFIG_UNIFIED, find_admission_rejection_events

NAMESPACE = "astronomer"

# Release name is "astronomer" (bin/helm-install.py), and charts/laminar's "laminar.fullname"
# is "<release>-<component>". The `component` POD label is not simply the name's suffix: the
# api-server's pods are labelled "apiserver", kept that way from the pre-Helm Kustomize
# manifests so the existing Services still select them (charts/laminar/templates/_helpers.yaml).
API_SERVER_DEPLOYMENT = "astronomer-api-server"
HYPERVISOR_DEPLOYMENT = "astronomer-hypervisor"
COMPONENT_LABELS = {API_SERVER_DEPLOYMENT: "apiserver", HYPERVISOR_DEPLOYMENT: "hypervisor"}
LAMINAR_DEPLOYMENTS = tuple(COMPONENT_LABELS)

REPORT_GROUP = "wgpolicyk8s.io"
REPORT_VERSION = "v1alpha2"
PASSING_RESULTS = {"pass", "skip"}


@pytest.fixture(scope="module")
def core_client() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def custom_objects_client() -> client.CustomObjectsApi:
    """Kyverno's PolicyReport CRD has no typed client."""
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CustomObjectsApi()


@pytest.fixture(scope="module")
def laminar_pod_uids(core_client) -> dict[str, set[str]]:
    """Each component's live pod UIDs, which is what report results are matched on below.

    UIDs rather than names because Kyverno's autogen rules also report against each pod's
    Deployment and ReplicaSet, and on a cluster this scenario has run against before those
    outnumber the pod results several times over."""
    pod_uids = {}
    for name in LAMINAR_DEPLOYMENTS:
        pods = core_client.list_namespaced_pod(NAMESPACE, label_selector=f"component={COMPONENT_LABELS[name]}").items
        pod_uids[name] = {pod.metadata.uid for pod in pods if pod.metadata.deletion_timestamp is None}
        assert pod_uids[name], f"No live pods found for {name}"
    return pod_uids


def test_no_admission_rejection_events(core_client):
    """Nothing was refused admission while the chart installed -- the blind spot auth-sidecar
    covers with test_no_psa_rejection_events.

    A refused pod is never created, so it leaves no unhealthy Pod object, only a FailedCreate
    Warning on the ReplicaSet that tried. Cannot fire from Kyverno while the scan is audit-only;
    it is here for another webhook refusing a Laminar pod, or for Audit being lifted."""
    rejections = [
        line
        for deployment_name in LAMINAR_DEPLOYMENTS
        for line in find_admission_rejection_events(core_client, NAMESPACE, deployment_name)
    ]
    assert not rejections, "Admission refused at least one Laminar pod:\n" + "\n".join(f"  {line}" for line in rejections)


def _laminar_results(reports: list[dict], pod_uids: set[str]) -> list[tuple[str, str, str, str]]:
    """(result, pod name, policy/rule, message) for every report entry about one of `pod_uids`.

    Pod kind and UID only, ignoring Kyverno's autogen results against the Deployment and
    ReplicaSet: accepting those would let the caller pass against a Kyverno that never evaluated
    a single Laminar pod.

    The `resources` fallback to the report's own `scope` mirrors bin/report-kyverno-scan.py --
    a result need not carry its own resources[] entry, and those that don't describe the
    report's subject."""
    return [
        (
            result.get("result", "?"),
            resource.get("name", ""),
            f"{result.get('policy', '?')}/{result.get('rule', '?')}",
            result.get("message", ""),
        )
        for report in reports
        for result in report.get("results", [])
        for resource in result.get("resources") or [report.get("scope") or {}]
        if resource.get("kind") == "Pod" and resource.get("uid") in pod_uids
    ]


# Kyverno's reports controller writes PolicyReports asynchronously, after the admission review it
# reports on has already let the pod through, so they can legitimately not be there yet.
@pytest.mark.flaky(reruns=12, reruns_delay=10)
def test_kyverno_evaluated_laminar_pods(laminar_pod_uids, custom_objects_client):
    """Kyverno produced results for both components' pods, and every result passed.

    Asserted as a pair, per component, because either half alone passes for the wrong reason:
    results nobody checks hide a real violation, and "no violations" with no results at all is
    exactly what a Kyverno matching nothing looks like -- most likely the `platform: astronomer`
    namespace label missing from test_profile.yaml, which every installed policy selects on.

    Failing on a violation is specific to this scenario. The scan is audit-only platform-wide
    (PINF-1034) because it is a report, not a gate; here Laminar is the thing under test, so a
    Laminar pod that stops satisfying the policies is a failure, not a line in a report."""
    reports = custom_objects_client.list_namespaced_custom_object(REPORT_GROUP, REPORT_VERSION, NAMESPACE, "policyreports")["items"]
    for deployment_name, pod_uids in laminar_pod_uids.items():
        results = _laminar_results(reports, pod_uids)
        assert results, (
            f"Kyverno produced no policy results for any {deployment_name} pod (uids: {sorted(pod_uids)}) in "
            f"the {NAMESPACE} namespace. Kyverno was installed before the chart, so these pods passed through "
            "admission -- no results means the policies matched nothing. Check that the namespace carries the "
            "`platform: astronomer` label from this scenario's test_profile.yaml."
        )
        violations = [entry for entry in results if entry[0] not in PASSING_RESULTS]
        assert not violations, f"{deployment_name} pods violate the installed Kyverno policies:\n" + "\n".join(
            f"  {outcome.upper()} {policy_rule} on {NAMESPACE}/{name}: {message}"
            for outcome, name, policy_rule, message in violations
        )
        print(f"Kyverno evaluated {len(results)} result(s) against {deployment_name} pods, all passing.")
