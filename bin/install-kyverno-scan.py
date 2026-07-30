#!/usr/bin/env python3
"""Install a real, live Kyverno admission controller into a test cluster, audit-only.

Installs the actual Kyverno Helm chart plus a set of Kyverno ClusterPolicy manifests,
and waits for them to be ready to evaluate resources. Call this before creating any of
the resources you want evaluated (i.e. before a test suite provisions its fixtures),
not afterward.

The reason to install a real, live admission controller instead of just running a
one-time `kyverno apply --cluster` scan at the end of a test run is that a live
controller evaluates every resource as it's created and keeps a permanent record
(see bin/report-kyverno-scan.py) of the result. A scan run only once, after the fact,
can only see whatever resources are still alive at that moment -- it will silently
miss a short-lived resource, such as a Job that runs to completion and is cleaned up
(e.g. a database-migration Job), even if that resource violated a policy while it
existed.

Every policy's validationFailureAction is force-overridden to Audit here, regardless
of what it's set to in the source policy file (some ship as Enforce), because this
tooling is meant only to report on policy compliance, never to block or fail a build
over it. See Linear ticket PINF-1034 for the background on why this exists.
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
# Pinned to the same Kyverno Helm chart version (which maps to Kyverno appVersion
# v1.18.2) that astronomer/apc-terraform-modules' own Terraform module installs for
# real customer clusters (its "kyverno_chart_version" input, defined in
# src/kyverno/variables.tf in that repo). Keeping the two in sync means this test is
# exercising the same policy-engine version real deployments actually run.
KYVERNO_CHART_VERSION = "3.8.2"

# The astronomer/apc-terraform-modules repo (private) is where Astronomer's actual
# Kyverno policies live, at the path below -- see that repo's src/kyverno/main.tf,
# which applies every *.yaml file under this same directory the same way this script
# does. If cloning starts failing, or this scan runs clean with suspiciously few
# results, check whether that repo moved the policies directory before assuming these
# two constants are still right.
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


def get_ready_condition_field(kubeconfig: str, name: str, field: str) -> str | None:
    """Read one field (status or message) off a ClusterPolicy's Ready condition, or None before it exists.

    Readiness is a status.conditions entry (type == "Ready"), not a top-level
    status.ready boolean -- Kyverno v1.18's ClusterPolicy CRD only defines
    status.conditions/status.rulecount, confirmed against its own CRD schema. A flat
    `-o jsonpath={.status.ready}` check always returns empty and can never see
    readiness, which is why this used to hang until the timeout with no explanation.
    """
    result = subprocess.run(
        [
            str(KUBECTL_EXE),
            f"--kubeconfig={kubeconfig}",
            "get",
            "clusterpolicy",
            name,
            "-o",
            f'jsonpath={{.status.conditions[?(@.type=="Ready")].{field}}}',
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def wait_for_policies_ready(kubeconfig: str, policy_names: list[str], timeout: int = 120) -> None:
    """Poll each ClusterPolicy's Ready condition until true, or raise on timeout.

    Applying a ClusterPolicy manifest and having Kyverno actually register and
    validate that policy against its admission webhook are two different moments --
    the object can exist in the API server before Kyverno has finished processing it.
    Any resource created in that gap would not be evaluated by the policy at all, so
    this function exists to make callers wait past that gap rather than assuming the
    policy is active as soon as `kubectl apply` returns.
    """
    deadline = time.monotonic() + timeout
    pending = set(policy_names)
    last_message: dict[str, str] = {}
    while pending:
        for name in list(pending):
            message = get_ready_condition_field(kubeconfig, name, "message")
            if message:
                last_message[name] = message
            if get_ready_condition_field(kubeconfig, name, "status") == "True":
                pending.discard(name)
        if not pending:
            return
        if time.monotonic() >= deadline:
            details = "\n".join(
                f"  {name}: {last_message.get(name, '(no Ready condition reported yet)')}" for name in sorted(pending)
            )
            raise SystemExit(f"ERROR: ClusterPolicy(s) never became ready within {timeout}s:\n{details}")
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
