#!/usr/bin/env python3
"""Report Kyverno policy violations, audit-only (PINF-1034).

Reads PolicyReport/ClusterPolicyReport objects (group wgpolicyk8s.io, version
v1alpha2 -- confirmed against Kyverno v1.18.2's own CRD manifests) rather than
running a point-in-time scan. These accumulate from real admission-time evaluations
made by the live controller bin/install-kyverno-scan.py installed earlier in this
job, and persist as their own objects independent of whatever resource they
describe -- so a short-lived resource (a Job that already completed and may be
cleaned up) that violated a policy while it existed still shows up here, unlike a
`kyverno apply --cluster` scan run only at this point, which can only see whatever's
still alive right now.

Never fails the build over violations found (prints them, that's the acceptance
criterion) -- only over a genuine failure to read reports at all (missing CRDs, API
errors), which means the scan itself didn't run, not that it found something.
"""

import argparse
import sys
from collections import Counter, defaultdict

from kubernetes import client, config

REPORT_GROUP = "wgpolicyk8s.io"
REPORT_VERSION = "v1alpha2"
PASSING_RESULTS = {"pass", "skip"}


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", required=True, help="Path to the kubeconfig for the cluster to read reports from.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Also print every individual scanned object -- its namespace, name, and result -- "
            "not just the non-passing ones. Useful for checking whether a given namespace was "
            "scanned at all, not only whether it had violations."
        ),
    )
    return parser.parse_args()


def resource_ref(result: dict, report: dict) -> tuple[str | None, str]:
    """(namespace, name) for a result -- its own resources[] entry if present,
    falling back to the report's own scope (its default subject) otherwise."""
    resources = result.get("resources") or [report.get("scope", {})]
    subject = resources[0]
    return subject.get("namespace"), subject.get("name", "?")


def describe_subject(result: dict, report: dict) -> str:
    """One resource reference for a result, formatted as namespace/name (or just name for a cluster-scoped resource)."""
    namespace, name = resource_ref(result, report)
    return f"{namespace}/{name}" if namespace else name


def summarize_reports(reports: list[dict]) -> list[str]:
    """One line per non-passing result across the given PolicyReport/ClusterPolicyReport items."""
    lines = []
    for report in reports:
        for result in report.get("results", []):
            if result.get("result") in PASSING_RESULTS:
                continue
            lines.append(
                f"{result.get('result', '?').upper()} {result.get('policy', '?')}/{result.get('rule', '?')} "
                f"on {describe_subject(result, report)}: {result.get('message', '')}"
            )
    return lines


def list_all_results(reports: list[dict]) -> list[str]:
    """One line per individual result across the given reports, regardless of pass/fail.

    Unlike summarize_reports() below, this includes passing results too. It exists so
    --verbose can show exactly which namespaces and objects were actually scanned, not
    just which ones failed -- a namespace that never appears here at all was never
    evaluated by anything, which looks nothing like a namespace full of passing pods
    once you can see the full list, but is indistinguishable from one if you can only
    see violations.
    """
    rows = []
    for report in reports:
        for result in report.get("results", []):
            namespace, name = resource_ref(result, report)
            rows.append(
                (
                    namespace or "(cluster-scoped)",
                    name,
                    result.get("policy", "?"),
                    result.get("rule", "?"),
                    result.get("result", "?"),
                )
            )
    rows.sort()
    return [f"ns={namespace} {name}: {policy}/{rule} -> {result.upper()}" for namespace, name, policy, rule, result in rows]


def count_evaluations(reports: list[dict]) -> dict[str, Counter]:
    """Per-policy count of each result type seen across the given reports.

    A policy is only evaluated against resources that match its own `match`/
    `namespaceSelector` rules. If nothing in the cluster matches (for example, because
    an expected namespace label was never applied), the policy produces zero results
    -- which looks identical, in summarize_reports() above, to a policy that was
    evaluated many times and never found a violation. This function exists to make
    that difference visible: a policy with an all-zero counter here was never
    actually evaluated against anything, which is a configuration problem, not a
    clean compliance result.
    """
    counts: dict[str, Counter] = defaultdict(Counter)
    for report in reports:
        for result in report.get("results", []):
            counts[result.get("policy", "?")][result.get("result", "?")] += 1
    return counts


def main() -> None:
    args = parse_args()
    config.load_kube_config(config_file=args.kubeconfig)
    api = client.CustomObjectsApi()

    # list_cluster_custom_object hits the collection-level (no-namespace-segment)
    # endpoint, which the k8s API serves across all namespaces for a namespaced CRD
    # like PolicyReport too, not just for genuinely cluster-scoped ones.
    cluster_reports = api.list_cluster_custom_object(REPORT_GROUP, REPORT_VERSION, "clusterpolicyreports")["items"]
    namespaced_reports = api.list_cluster_custom_object(REPORT_GROUP, REPORT_VERSION, "policyreports")["items"]

    if args.verbose:
        print("--- Kyverno scanned objects (verbose, includes passing results) ---")
        for line in list_all_results(cluster_reports + namespaced_reports):
            print(line)

    # The definitive list of policies that were actually installed -- these persist as
    # their own ClusterPolicy objects from bin/install-kyverno-scan.py, independent of
    # whether any report ever mentions them. Used below to catch a policy that matched
    # zero resources, which otherwise looks identical to a policy with zero violations.
    installed_policies = sorted(
        item["metadata"]["name"] for item in api.list_cluster_custom_object("kyverno.io", "v1", "clusterpolicies")["items"]
    )
    counts = count_evaluations(cluster_reports + namespaced_reports)

    print("--- Kyverno policy evaluation counts ---")
    for policy in installed_policies:
        counter = counts.get(policy)
        if not counter:
            print(f"{policy}: NO RESULTS -- matched zero resources, this policy was never actually evaluated")
        else:
            print(f"{policy}: {dict(counter)}")

    findings = summarize_reports(cluster_reports) + summarize_reports(namespaced_reports)
    print(f"--- Kyverno policy report findings ({len(findings)}) ---")
    for line in findings:
        print(line)
    if not findings:
        print("No non-passing results found.")
    else:
        print("Not failing the build over these -- audit-only, see PINF-1034.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: reading Kyverno policy reports failed: {e}", file=sys.stderr)
        raise SystemExit(1) from e
