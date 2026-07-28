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
    return parser.parse_args()


def describe_subject(result: dict, report: dict) -> str:
    """One resource reference for a result -- its own resources[] entry if present,
    falling back to the report's own scope (its default subject) otherwise."""
    resources = result.get("resources") or [report.get("scope", {})]
    subject = resources[0]
    namespace = subject.get("namespace")
    name = subject.get("name", "?")
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


def count_evaluations(reports: list[dict]) -> dict[str, Counter]:
    """Per-policy count of each result type seen across the given reports.

    A policy whose namespaceSelector matches zero resources produces zero results,
    which prints identically to "zero violations" in summarize_reports() above --
    the exact ambiguity this repo's own notes warn about (a missing namespace label
    makes the scan "run clean" by matching nothing, not because nothing's wrong).
    This makes that distinction visible: a policy with an all-zero counter here
    never actually got evaluated against anything.
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
    print("Not failing the build over these -- audit-only, see PINF-1034.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: reading Kyverno policy reports failed: {e}", file=sys.stderr)
        raise SystemExit(1) from e
