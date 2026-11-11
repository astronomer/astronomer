"""Every workload that waits for Commander or the registry must be admitted by that service's NetworkPolicy.

Houston's entrypoint blocks, with no timeout, until it can open a TCP connection to Commander
(COMMANDER_WAIT_ENABLED) and to the registry (REGISTRY_WAIT_ENABLED). In unified mode with network
policies on, a workload whose component label is missing from the target's NetworkPolicy waits
forever. A CronJob with concurrencyPolicy: Forbid then skips every later run. dp-link (#3730) and
houston-cleanup-cluster-audits (#3754 for Commander, and again for the registry) each shipped with
this gap, so this test checks every rendered pod template instead of one label at a time.
"""

import pytest

from tests.utils import get_containers_by_name, get_pod_template
from tests.utils.chart import render_chart

# Every Houston job that has its own on/off switch, turned on so its pod template is rendered.
HOUSTON_JOB_SWITCHES = [
    "upgradeDeployments",
    "cleanupDeployments",
    "cleanupDeployRevisions",
    "cleanupClusterAudits",
    "updateCheck",
    "updateRuntimeCheck",
    "syncDataplaneClusters",
]

# Waiting workloads that only render behind a switch the fixture turns on. If one stops rendering,
# the fixture has drifted from the chart and the test would pass without checking it.
GATED_WAITING_COMPONENTS = {
    "houston-cleanup-cluster-audits",
    "houston-cp-refresh",
    "houston-populate-daily-task-metrics",
    "houston-populate-hourly-ta-metrics",
    "houston-sync-dataplane-clusters",
    "houston-update-check",
    "houston-update-runtime-check",
}

# The wait flag each policy has to satisfy, keyed by the NetworkPolicy's component label.
POLICIES = {
    "commander-policy": "COMMANDER_WAIT_ENABLED",
    "registry-policy": "REGISTRY_WAIT_ENABLED",
}


@pytest.fixture(scope="module")
def unified_docs():
    return render_chart(
        values={
            "global": {
                "networkPolicy": {"enabled": True},
                "plane": {"mode": "unified"},
                # Off by default. Each gates Houston workloads that wait for Commander and the registry:
                # the task-usage CronJobs, and the houston-cp-refresh hook.
                "metricsReporting": {"taskUsageMetrics": {"enabled": True}},
                "controlPlaneHA": {"enabled": True, "globalBaseDomain": "example.com"},
            },
            "astronomer": {"houston": {switch: {"enabled": True} for switch in HOUSTON_JOB_SWITCHES}},
        },
    )


def _admitted_components(policy: dict) -> set[str]:
    """Component labels of the same-release astronomer pods that the policy's ingress rules admit."""
    return {
        peer["podSelector"]["matchLabels"]["component"]
        for rule in policy["spec"]["ingress"]
        for peer in rule.get("from", [])
        if peer.get("podSelector", {}).get("matchLabels", {}).get("tier") == "astronomer"
        and peer["podSelector"]["matchLabels"].get("release") == "release-name"
    }


def _waiting_workloads(docs: list[dict], wait_var: str) -> dict[str, str]:
    """Component label -> "Kind/name" for every pod template with a container that sets wait_var to "true"."""
    waiting = {}
    for doc in docs:
        template = get_pod_template(doc)
        if not template:
            continue
        containers = get_containers_by_name(doc, include_init_containers=True).values()
        if any(env.get("name") == wait_var and env.get("value") == "true" for c in containers for env in c.get("env") or []):
            component = template.get("metadata", {}).get("labels", {}).get("component")
            waiting[component] = f"{doc['kind']}/{doc['metadata']['name']}"
    return waiting


@pytest.mark.parametrize("policy_component,wait_var", POLICIES.items())
def test_unified_networkpolicy_admits_every_workload_that_waits_for_it(unified_docs, policy_component, wait_var):
    (policy,) = [
        doc
        for doc in unified_docs
        if doc["kind"] == "NetworkPolicy" and (doc["metadata"].get("labels") or {}).get("component") == policy_component
    ]
    waiting = _waiting_workloads(unified_docs, wait_var)
    not_rendered = GATED_WAITING_COMPONENTS - waiting.keys()
    assert not not_rendered, f"the fixture no longer renders {sorted(not_rendered)} with {wait_var}=true, so they go unchecked"

    missing = {component: workload for component, workload in waiting.items() if component not in _admitted_components(policy)}

    assert not missing, f"{policy_component} does not admit these workloads that wait on it ({wait_var}=true): {missing}"
