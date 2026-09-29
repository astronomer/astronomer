#!/usr/bin/env python3

"""Adopt bootstrapper-created Secrets into a Helm release before `helm upgrade`.

Some Secrets that the Astronomer chart now renders as release-managed manifests
(for example ``<release>-flightdeck-backend``) were, in older releases, created
out of band by a bootstrapper init container and therefore carry no Helm
ownership metadata. Helm 3 refuses to adopt a live resource it did not create,
so ``helm upgrade`` aborts with:

    Secret "<release>-flightdeck-backend" ... cannot be imported into the
    current release: invalid ownership metadata; missing key
    "app.kubernetes.io/managed-by": must be set to "Helm"

Helm performs this ownership check in its prepare phase, *before* it runs any
pre-upgrade hook, so the conflict cannot be repaired from inside the chart.
This script stamps the required Helm ownership label and annotations onto the
live Secret(s) so the next ``helm upgrade`` can adopt them.

It is idempotent and safe to run before every upgrade: a Secret that does not
exist (fresh install, or FlightDeck disabled) or that is already owned by this
release is left untouched. A Secret owned by a *different* release is never
reassigned -- the script errors out so the conflict is resolved deliberately.

Usage:
    ./bin/adopt-bootstrap-secrets-pre-upgrade.py
    ./bin/adopt-bootstrap-secrets-pre-upgrade.py --release-name astronomer --namespace astronomer
    ./bin/adopt-bootstrap-secrets-pre-upgrade.py --dry-run
    ./bin/adopt-bootstrap-secrets-pre-upgrade.py --secret my-release-flightdeck-backend
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
RELEASE_NAME_ANNOTATION = "meta.helm.sh/release-name"
RELEASE_NAMESPACE_ANNOTATION = "meta.helm.sh/release-namespace"

# Secret name suffixes that the secrets-from-files feature newly renders as
# release-managed manifests but that older releases created unmanaged via a
# bootstrapper init container. Prefixed with the release name at runtime.
DEFAULT_SECRET_SUFFIXES = ["flightdeck-backend"]


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing stdout/stderr as text.

    Parameters:
        cmd: Argument vector to execute.
        check: Raise CalledProcessError on a non-zero exit when True.

    Returns:
        The completed process.
    """
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def kubectl_base(kubectl: str, namespace: str, context: str | None) -> list[str]:
    """Build the common kubectl argument prefix (binary + namespace + context)."""
    base = [kubectl, "--namespace", namespace]
    if context:
        base += ["--context", context]
    return base


def get_secret(base: list[str], name: str) -> dict | None:
    """Fetch a Secret as a dict, or None if it does not exist.

    Raises:
        RuntimeError: If kubectl fails for any reason other than not-found.
    """
    proc = run([*base, "get", "secret", name, "-o", "json"], check=False)
    if proc.returncode == 0:
        return json.loads(proc.stdout)
    if "NotFound" in proc.stderr or "not found" in proc.stderr:
        return None
    raise RuntimeError(f"kubectl get secret {name} failed: {proc.stderr.strip()}")


def needs_adoption(secret: dict, release_name: str, release_namespace: str) -> bool:
    """Return True if the Secret lacks correct Helm ownership metadata.

    Parameters:
        secret: The Secret object as returned by ``kubectl get -o json``.
        release_name: The Helm release that should own the Secret.
        release_namespace: The namespace of that release.

    Returns:
        True when the Secret is unmanaged and should be stamped; False when it
        is already owned by this release.

    Raises:
        RuntimeError: If the Secret is already owned by a *different* release,
            which this script refuses to clobber.
    """
    meta = secret.get("metadata", {})
    labels = meta.get("labels") or {}
    annotations = meta.get("annotations") or {}
    managed_by = labels.get(MANAGED_BY_LABEL)
    owner_name = annotations.get(RELEASE_NAME_ANNOTATION)
    owner_ns = annotations.get(RELEASE_NAMESPACE_ANNOTATION)

    already_ours = managed_by == "Helm" and owner_name == release_name and owner_ns == release_namespace
    if already_ours:
        return False

    owned_by_other = managed_by == "Helm" or owner_name is not None or owner_ns is not None
    if owned_by_other:
        raise RuntimeError(
            f"Secret {meta.get('name')!r} already carries Helm ownership metadata for a "
            f"different release (managed-by={managed_by!r}, release-name={owner_name!r}, "
            f"release-namespace={owner_ns!r}); refusing to reassign it. Resolve this "
            "conflict manually before upgrading."
        )
    return True


def adopt_secret(base: list[str], name: str, release_name: str, release_namespace: str, dry_run: bool) -> None:
    """Stamp the Helm ownership label + annotations onto a live Secret.

    Raises:
        subprocess.CalledProcessError: If a kubectl invocation fails.
    """
    label_cmd = [*base, "label", "secret", name, "--overwrite", f"{MANAGED_BY_LABEL}=Helm"]
    annotate_cmd = [
        *base,
        "annotate",
        "secret",
        name,
        "--overwrite",
        f"{RELEASE_NAME_ANNOTATION}={release_name}",
        f"{RELEASE_NAMESPACE_ANNOTATION}={release_namespace}",
    ]
    if dry_run:
        print(f"  [dry-run] would run: {' '.join(label_cmd)}")
        print(f"  [dry-run] would run: {' '.join(annotate_cmd)}")
        return
    run(label_cmd)
    run(annotate_cmd)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--release-name", default="astronomer", help="Helm release name (default: astronomer)")
    parser.add_argument("--namespace", default="astronomer", help="Release namespace (default: astronomer)")
    parser.add_argument("--kube-context", default=None, help="kubectl context to use (default: current context)")
    parser.add_argument("--kubectl", default="kubectl", help="Path to the kubectl binary (default: kubectl)")
    parser.add_argument(
        "--secret",
        dest="secrets",
        action="append",
        default=None,
        help="Explicit Secret name to adopt (repeatable). Defaults to the known bootstrapper-created Secrets for the release.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without modifying anything")
    args = parser.parse_args(argv)

    secrets = args.secrets or [f"{args.release_name}-{suffix}" for suffix in DEFAULT_SECRET_SUFFIXES]
    base = kubectl_base(args.kubectl, args.namespace, args.kube_context)

    adopted: list[str] = []
    skipped: list[str] = []
    for name in secrets:
        try:
            secret = get_secret(base, name)
            if secret is None:
                print(f"SKIP  {name}: not found (fresh install, or FlightDeck disabled) - nothing to adopt")
                skipped.append(name)
                continue
            if not needs_adoption(secret, args.release_name, args.namespace):
                print(f"SKIP  {name}: already owned by release {args.release_name!r} - nothing to do")
                skipped.append(name)
                continue
            print(f"ADOPT {name}: stamping Helm ownership metadata for release {args.release_name!r}")
            adopt_secret(base, name, args.release_name, args.namespace, args.dry_run)
            adopted.append(name)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        except subprocess.CalledProcessError as exc:
            print(f"ERROR: failed to adopt {name}: {(exc.stderr or '').strip()}", file=sys.stderr)
            return 1

    print()
    verb = "would adopt" if args.dry_run else "adopted"
    print(f"Done. {verb} {len(adopted)} secret(s); skipped {len(skipped)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
