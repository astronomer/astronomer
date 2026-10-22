"""Laminar (api-server + hypervisor) under a live Kyverno admission controller.

What this scenario is able to prove, and why it is shaped this way:

The scenario mechanism installs Kyverno (bin/install-kyverno-scan.py) *after* the platform
chart, and forces every policy to Audit. Both of those matter here:

  - Installed after the chart, Kyverno never saw the pods `helm install` created. A test that
    only asserted "the Laminar pods are Ready" would therefore say nothing at all about
    Kyverno -- those pods predate it. The roll in `rolled_laminar_deployments` below exists to
    fix that: it recreates both Deployments' pods while the webhook is live, which is the only
    moment their pod specs actually pass through admission (and through any Kyverno mutation).

  - Audit-only, Kyverno cannot block anything, so a failed admission can never surface as a
    failed install. The failure mode this file is built to catch is the one that remains: a
    Kyverno *mutate* rule rewriting the pod spec into something that will not start, or a
    policy that stalls admission long enough to blow the rollout deadline.

`test_kyverno_evaluated_laminar_objects` guards the whole file against the quiet failure: a
Kyverno that is running but matches no Laminar object produces exactly the same green run as a
Laminar that is fully compliant. See bin/report-kyverno-scan.py's count_evaluations() for the
same concern applied to the scan as a whole.

Module-scoped clients built directly from KUBECONFIG_UNIFIED, rather than the function-scoped
fixtures in tests/functional/conftest.py: the roll below is the expensive part of this scenario
and has to happen once for the whole module, which a module-scoped fixture cannot do on top of
function-scoped ones. Same pattern as custom-image-sha and git-sync-shared-volume.
"""

import time

import pytest
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from tests.utils.k8s import KUBECONFIG_UNIFIED

NAMESPACE = "astronomer"

# Release name is "astronomer" (bin/helm-install.py), and charts/laminar's "laminar.fullname"
# is "<release>-<component>". The `component` POD label is not simply the name's suffix: the
# api-server's pods are labelled "apiserver", kept that way from the pre-Helm Kustomize
# manifests so the existing Services still select them (charts/laminar/templates/_helpers.yaml).
API_SERVER_DEPLOYMENT = "astronomer-api-server"
HYPERVISOR_DEPLOYMENT = "astronomer-hypervisor"
COMPONENT_LABELS = {API_SERVER_DEPLOYMENT: "apiserver", HYPERVISOR_DEPLOYMENT: "hypervisor"}
LAMINAR_DEPLOYMENTS = tuple(COMPONENT_LABELS)

# charts/laminar/values.yaml gives the api-server a startupProbe of 30 x 10s on top of two init
# containers, and the hypervisor rolls with strategy Recreate (down to zero, then back up). The
# chart's own progressDeadlineSeconds is 1200; this stays under it so a stuck roll fails here,
# with the Deployment's own status to look at, rather than hanging to the suite timeout.
ROLLOUT_TIMEOUT_SECONDS = 600
ROLLOUT_POLL_SECONDS = 5

KYVERNO_GROUP = "kyverno.io"
KYVERNO_VERSION = "v1"
REPORT_GROUP = "wgpolicyk8s.io"
REPORT_VERSION = "v1alpha2"
PASSING_RESULTS = {"pass", "skip"}


@pytest.fixture(scope="module")
def apps_client() -> client.AppsV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AppsV1Api()


@pytest.fixture(scope="module")
def core_client() -> client.CoreV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CoreV1Api()


@pytest.fixture(scope="module")
def custom_objects_client() -> client.CustomObjectsApi:
    """Kyverno's ClusterPolicy and the PolicyReport CRDs have no typed client."""
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.CustomObjectsApi()


@pytest.fixture(scope="module")
def webhook_client() -> client.AdmissionregistrationV1Api:
    config.load_kube_config(config_file=KUBECONFIG_UNIFIED)
    return client.AdmissionregistrationV1Api()


def _ready_clusterpolicies(custom_objects_client) -> list[str]:
    """Names of the ClusterPolicies currently reporting Ready, or [] when Kyverno is not installed.

    Readiness is a status.conditions entry, not a top-level status.ready boolean -- Kyverno
    v1.18's ClusterPolicy CRD only defines status.conditions/status.rulecount. A policy object
    can exist in the API server before Kyverno has registered it with the admission webhook, and
    anything created in that gap is not evaluated at all, so "the object exists" is not the
    question being asked here.
    """
    try:
        policies = custom_objects_client.list_cluster_custom_object(KYVERNO_GROUP, KYVERNO_VERSION, "clusterpolicies")["items"]
    except ApiException as exc:
        # 404 means the CRD itself is absent, i.e. Kyverno was never installed into this cluster.
        if exc.status == 404:
            return []
        raise
    return [
        policy["metadata"]["name"]
        for policy in policies
        if any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in (policy.get("status") or {}).get("conditions") or []
        )
    ]


@pytest.fixture(scope="module")
def ready_clusterpolicies(custom_objects_client) -> list[str]:
    """Skip this module's Kyverno-dependent tests when no Kyverno is live in the cluster.

    bin/run-scenario.py does not install Kyverno -- only the generated CI job does, between
    run-scenario.py and pytest. A bare local run therefore has no Kyverno, and every test that
    depends on one would otherwise pass without testing anything.
    """
    policies = _ready_clusterpolicies(custom_objects_client)
    if not policies:
        pytest.skip(
            "No Ready Kyverno ClusterPolicy found -- Kyverno is not live in this cluster. "
            "Install it between bin/run-scenario.py and pytest, the way the CI job does:\n"
            "  uv run bin/install-kyverno-scan.py "
            '--kubeconfig="${HOME}/.local/share/astronomer-software/kubeconfig/unified"\n'
            "(needs a GITHUB_TOKEN with read access to astronomer/apc-terraform-modules)."
        )
    return policies


def _rollout_complete(deployment) -> bool:
    """Whether every replica of `deployment` is on the current pod template and Ready.

    observed_generation is checked first and deliberately: immediately after a patch, the
    Deployment's status still describes the *previous* template, so updated_replicas and
    ready_replicas both already read "complete" for a roll that has not started yet. Without
    this check the poll below returns on its first iteration, every time.
    """
    status = deployment.status
    if (status.observed_generation or 0) < (deployment.metadata.generation or 0):
        return False
    expected = deployment.spec.replicas or 0
    return (
        (status.updated_replicas or 0) == expected
        and (status.ready_replicas or 0) == expected
        and (status.unavailable_replicas or 0) == 0
    )


def _wait_for_rollout(apps_client, name: str) -> None:
    """Block until `name` has finished rolling, or fail with its last observed status."""
    deadline = time.monotonic() + ROLLOUT_TIMEOUT_SECONDS
    while True:
        deployment = apps_client.read_namespaced_deployment(name, NAMESPACE)
        if _rollout_complete(deployment):
            return
        if time.monotonic() >= deadline:
            pytest.fail(
                f"Deployment {NAMESPACE}/{name} did not finish rolling within {ROLLOUT_TIMEOUT_SECONDS}s "
                f"under a live Kyverno admission controller. Last status: {deployment.status}"
            )
        time.sleep(ROLLOUT_POLL_SECONDS)


@pytest.fixture(scope="module")
def rolled_laminar_deployments(apps_client, ready_clusterpolicies) -> None:
    """Recreate both Laminar Deployments' pods with Kyverno live, then wait for both to settle.

    The annotation patch is what `kubectl rollout restart` does -- it changes the pod template,
    which is what forces new pods, and therefore fresh admission reviews. Restarting is not a
    side effect here, it is the test: the pods created by the earlier `helm install` never went
    through Kyverno at all.

    Both patches are sent before either wait, so the two components roll concurrently rather
    than end to end -- the api-server's startupProbe budget alone is 300s.
    """
    restarted_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    patch = {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": restarted_at}}}}}
    for name in LAMINAR_DEPLOYMENTS:
        apps_client.patch_namespaced_deployment(name, NAMESPACE, patch)
    for name in LAMINAR_DEPLOYMENTS:
        _wait_for_rollout(apps_client, name)


@pytest.mark.parametrize("deployment_name", LAMINAR_DEPLOYMENTS)
def test_laminar_deployment_is_available(apps_client, deployment_name):
    """Both Laminar Deployments are fully Ready as installed.

    Unconditional, with no Kyverno involved: it is the baseline the Kyverno tests are measured
    against, and the one assertion in this file that still means something on a local run where
    Kyverno was never installed. Readiness is not a weak check here -- charts/laminar's
    readinessProbe is an HTTP GET of /laminar/healthz against the app itself, so a Ready replica
    is one whose Laminar process is answering.
    """
    deployment = apps_client.read_namespaced_deployment(deployment_name, NAMESPACE)
    expected = deployment.spec.replicas
    assert (deployment.status.ready_replicas or 0) == expected, (
        f"{deployment_name}: expected {expected} ready replica(s), got {deployment.status.ready_replicas}"
    )


def test_kyverno_admission_is_live(ready_clusterpolicies, webhook_client):
    """Kyverno is installed with at least one Ready policy AND a registered admission webhook.

    A Ready ClusterPolicy on its own is not enough: without a registered
    ValidatingWebhookConfiguration nothing is ever routed to Kyverno, and every pod is admitted
    unevaluated. Both halves have to hold before any assertion about behaviour "under Kyverno"
    means anything.
    """
    webhooks = [
        webhook.metadata.name
        for webhook in webhook_client.list_validating_webhook_configuration().items
        if "kyverno" in webhook.metadata.name
    ]
    assert webhooks, (
        f"{len(ready_clusterpolicies)} Ready ClusterPolicy(ies) exist but no Kyverno "
        "ValidatingWebhookConfiguration is registered, so nothing is actually being evaluated."
    )
    print(f"Kyverno live: {len(ready_clusterpolicies)} Ready policy(ies), webhooks {webhooks}")


@pytest.mark.parametrize("deployment_name", LAMINAR_DEPLOYMENTS)
def test_laminar_recovers_after_rolling_under_kyverno(rolled_laminar_deployments, apps_client, deployment_name):
    """Every replica comes back Ready after being recreated through the live admission webhook.

    This is the scenario's point. `rolled_laminar_deployments` already waited for the roll (and
    fails there, with the Deployment's own status, if it stalls); this re-reads the Deployment so
    a failure is attributed to the component that did not come back, rather than to both.
    """
    deployment = apps_client.read_namespaced_deployment(deployment_name, NAMESPACE)
    expected = deployment.spec.replicas
    assert (deployment.status.ready_replicas or 0) == expected, (
        f"{deployment_name}: only {deployment.status.ready_replicas} of {expected} replica(s) came "
        "back Ready after being recreated under a live Kyverno admission controller"
    )


@pytest.mark.parametrize("deployment_name", LAMINAR_DEPLOYMENTS)
def test_laminar_pods_restart_cleanly_under_kyverno(rolled_laminar_deployments, core_client, deployment_name):
    """No Laminar container crash-looped on the way back up.

    A Deployment can reach its ready count with a container that crashed several times first --
    a mutated securityContext that breaks the laminar-bootstrapper init container until some
    retry happens to succeed, say. Ready replicas alone hide that; restart counts do not.

    Pods already being deleted are excluded. A rolling update's outgoing pods still match the
    selector for a while after the Deployment reports complete, and they are pods Kyverno never
    admitted -- counting a restart they picked up during the original install would fail this
    test for something that happened before Kyverno existed.
    """
    label_selector = f"release=astronomer,tier=laminar,component={COMPONENT_LABELS[deployment_name]}"
    pods = [
        pod
        for pod in core_client.list_namespaced_pod(NAMESPACE, label_selector=label_selector).items
        if pod.metadata.deletion_timestamp is None
    ]
    assert pods, f"No live pods found for {deployment_name} (selector: {label_selector}) after the roll"
    offenders = [
        f"{pod.metadata.name}/{status.name} restarted {status.restart_count}x"
        for pod in pods
        for status in (pod.status.container_statuses or []) + (pod.status.init_container_statuses or [])
        if status.restart_count
    ]
    assert not offenders, "Laminar containers restarted after admission by Kyverno: " + "; ".join(offenders)


def _laminar_results(reports: list[dict]) -> list[tuple[str, str, str, str]]:
    """(result, object name, policy/rule, message) for every report entry about a Laminar object.

    Matches on the Deployment-name prefix rather than an exact pod name, so one pass covers the
    Pod, its ReplicaSet and the Deployment itself -- Kyverno reports against all three, and which
    one carries a given rule's result is the policy author's choice, not ours.

    The `resources` fallback to the report's own `scope` mirrors bin/report-kyverno-scan.py: a
    result does not have to carry its own resources[] entry, and the ones that don't describe
    the report's subject.
    """
    matched = []
    for report in reports:
        for result in report.get("results", []):
            resources = result.get("resources") or [report.get("scope") or {}]
            name = resources[0].get("name", "")
            if name.startswith(LAMINAR_DEPLOYMENTS):
                matched.append(
                    (
                        result.get("result", "?"),
                        name,
                        f"{result.get('policy', '?')}/{result.get('rule', '?')}",
                        result.get("message", ""),
                    )
                )
    return matched


# Kyverno's reports controller writes PolicyReports asynchronously, well after the admission
# review it is reporting on has already let the pod through. Reading them the moment the roll
# finishes can legitimately find nothing yet, so retry rather than assert once -- the repo's
# standard treatment for eventually-consistent cluster state.
@pytest.mark.flaky(reruns=12, reruns_delay=10)
def test_kyverno_evaluated_laminar_objects(rolled_laminar_deployments, custom_objects_client):
    """Kyverno actually produced results for Laminar objects; report any that did not pass.

    Without this, every other Kyverno assertion in this file is satisfied just as well by a
    Kyverno that matched nothing at all -- the likeliest cause being the `platform: astronomer`
    namespace label in test_profile.yaml going missing, since the chart does not apply it to the
    platform namespace itself and every installed policy selects on it.

    Non-passing results are printed, not asserted on. The scan is audit-only by design
    (PINF-1034): this scenario's acceptance criterion is that Laminar keeps *operating* under
    Kyverno, and turning a policy violation red here would quietly re-scope that into a
    compliance gate the rest of the platform is not held to.
    """
    reports = custom_objects_client.list_namespaced_custom_object(REPORT_GROUP, REPORT_VERSION, NAMESPACE, "policyreports")["items"]
    results = _laminar_results(reports)
    assert results, (
        f"Kyverno produced no policy results for {' or '.join(LAMINAR_DEPLOYMENTS)} in the {NAMESPACE} "
        "namespace. The pods were rolled while Kyverno was live, so this means the policies matched "
        "nothing here -- check that the namespace carries the `platform: astronomer` label from this "
        "scenario's test_profile.yaml."
    )
    print(f"Kyverno evaluated {len(results)} result(s) against Laminar objects.")
    violations = [entry for entry in results if entry[0] not in PASSING_RESULTS]
    for outcome, name, policy_rule, message in violations:
        print(f"  {outcome.upper()} {policy_rule} on {NAMESPACE}/{name}: {message}")
    if violations:
        print(f"{len(violations)} non-passing result(s) -- not failing the build, audit-only (PINF-1034).")
