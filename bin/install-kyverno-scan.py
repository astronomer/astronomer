#!/usr/bin/env python3
"""Install the real Kyverno admission controller + policies, audit-only (PINF-1034).

Run this BEFORE the scenario provisions anything (before bin/run-scenario.py, not
after it) -- the point of installing the real controller rather than just running
`kyverno apply --cluster` at the end is a live admission webhook that evaluates every
resource as it's created. A point-in-time scan run only at the end can't see a
short-lived resource (a Job like migrateDatabaseJob or houston-db-migrations that
completes and may get cleaned up) that already came and went by then; a live webhook
running for the scenario's whole lifetime catches it regardless, via
bin/report-kyverno-scan.py reading the PolicyReport/ClusterPolicyReport objects this
produces (those persist as their own objects independent of whatever resource they
describe).

Every policy's validationFailureAction is force-overridden to Audit here regardless of
its own real-world setting (two of the three current policies are Enforce) -- this
scan must never actually reject anything the scenario creates, matching PINF-1034's
explicit "don't fail the build" scope.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

GIT_ROOT_DIR = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)
HELM_EXE = Path.home() / ".local" / "share" / "astronomer-software" / "bin" / "helm"
KUBECTL_EXE = Path.home() / ".local" / "share" / "astronomer-software" / "bin" / "kubectl"

KYVERNO_NAMESPACE = "kyverno"
# Matches astronomer/apc-terraform-modules' real Terraform pin for the actual
# admission controller (its kyverno_chart_version input) -- confirmed this maps to
# appVersion v1.18.2, the same version this scan used before it ran the standalone
# CLI instead of the real controller.
KYVERNO_CHART_VERSION = "3.8.2"

# Verified by reading the real Terraform, not guessed: openshift-automation's
# modules/platform/kyverno.tf pulls this exact module/path for its own Kyverno install.
# If this scan starts erroring on clone, or runs clean with suspiciously few results,
# re-trace that chain before assuming these two constants are still right.
POLICIES_REPO = "astronomer/apc-terraform-modules"
POLICIES_PATH = "src/kyverno/policies"

VALIDATION_FAILURE_ACTION_RE = re.compile(r"^(\s*validationFailureAction:\s*)\S+", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", required=True, help="Path to the kubeconfig for the cluster to install into.")
    return parser.parse_args()


def clone_policies(dest: Path) -> Path:
    """Sparse-clone just POLICIES_PATH out of POLICIES_REPO (a private repo) into dest.

    Requires a GITHUB_TOKEN env var with read access to POLICIES_REPO -- CircleCI's
    `github-repo` context provides this (already used elsewhere in this pipeline for
    the same kind of private cross-repo access, e.g. bin/release-bom).
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit(
            f"ERROR: GITHUB_TOKEN is required to clone the private {POLICIES_REPO} repo "
            "(CircleCI's github-repo context provides this)."
        )
    url = f"https://{token}@github.com/{POLICIES_REPO}.git"
    subprocess.run(
        ["git", "clone", "--quiet", "--depth=1", "--filter=blob:none", "--sparse", url, str(dest)],
        check=True,
    )
    subprocess.run(["git", "-C", str(dest), "sparse-checkout", "set", POLICIES_PATH], check=True)
    policies_dir = dest / POLICIES_PATH
    if not policies_dir.is_dir():
        raise SystemExit(f"ERROR: {POLICIES_PATH} not found in {POLICIES_REPO} after clone -- did it move again?")
    return policies_dir


def force_audit_mode(policies_dir: Path) -> None:
    """Rewrite every policy's validationFailureAction to Audit in place, whatever it was."""
    for policy_file in policies_dir.glob("*.yaml"):
        text = policy_file.read_text()
        patched, count = VALIDATION_FAILURE_ACTION_RE.subn(r"\1Audit", text)
        if count:
            policy_file.write_text(patched)


def load_policy_names(policies_dir: Path) -> list[str]:
    """Read metadata.name out of each policy file -- used to poll ClusterPolicy readiness below."""
    return [yaml.safe_load(policy_file.read_text())["metadata"]["name"] for policy_file in policies_dir.glob("*.yaml")]


def install_kyverno_chart(kubeconfig: str) -> None:
    """Install (or upgrade) the real Kyverno Helm chart, waiting for it to be Ready."""
    subprocess.run(
        [str(HELM_EXE), "repo", "add", "--force-update", "kyverno", "https://kyverno.github.io/kyverno/"],
        check=True,
    )
    subprocess.run([str(HELM_EXE), "repo", "update", "kyverno"], check=True)
    subprocess.run(
        [
            str(HELM_EXE),
            "upgrade",
            "--install",
            "kyverno",
            "kyverno/kyverno",
            f"--version={KYVERNO_CHART_VERSION}",
            f"--namespace={KYVERNO_NAMESPACE}",
            "--create-namespace",
            f"--kubeconfig={kubeconfig}",
            "--wait",
            "--timeout=5m",
        ],
        check=True,
    )


def apply_policies(kubeconfig: str, policies_dir: Path) -> None:
    """Apply the (already audit-forced) ClusterPolicy manifests."""
    subprocess.run([str(KUBECTL_EXE), f"--kubeconfig={kubeconfig}", "apply", "-f", str(policies_dir)], check=True)


def wait_for_policies_ready(kubeconfig: str, policy_names: list[str], timeout: int = 120) -> None:
    """Poll each ClusterPolicy's status.ready until true, or raise on timeout.

    Resources created before a policy's own webhook configuration is actually live
    (not just the pod Ready, the policy itself registered and validated) wouldn't be
    evaluated at all -- this is the same kind of pod-Ready-vs-actually-reachable gap
    PINF-1049 hit with commander's JWKS fetch, just for a different component.
    """
    deadline = time.monotonic() + timeout
    pending = set(policy_names)
    while pending:
        for name in list(pending):
            result = subprocess.run(
                [
                    str(KUBECTL_EXE),
                    f"--kubeconfig={kubeconfig}",
                    "get",
                    "clusterpolicy",
                    name,
                    "-o",
                    "jsonpath={.status.ready}",
                ],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip() == "true":
                pending.discard(name)
        if not pending:
            return
        if time.monotonic() >= deadline:
            raise SystemExit(f"ERROR: ClusterPolicy(s) never became ready within {timeout}s: {sorted(pending)}")
        print(f"Waiting for ClusterPolicy readiness: {sorted(pending)} ({int(deadline - time.monotonic())}s remaining)")
        time.sleep(5)


def main() -> None:
    args = parse_args()
    install_kyverno_chart(args.kubeconfig)
    with tempfile.TemporaryDirectory() as tmp:
        policies_dir = clone_policies(Path(tmp) / "apc-terraform-modules")
        force_audit_mode(policies_dir)
        policy_names = load_policy_names(policies_dir)
        apply_policies(args.kubeconfig, policies_dir)
        wait_for_policies_ready(args.kubeconfig, policy_names)
    print(f"Kyverno controller + {len(policy_names)} policy(ies) (forced audit-only) ready: {sorted(policy_names)}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: kyverno install failed: {e}", file=sys.stderr)
        raise SystemExit(1) from e
