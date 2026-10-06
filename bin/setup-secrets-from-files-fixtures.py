#!/usr/bin/env python3
"""Pre-helm setup for the secrets-from-files scenario.

Runs via test_profile.yaml's `pre_helm_scripts` -- after the cluster exists but BEFORE
`helm install` (see tests/functional/scenarios/README.md). It must run pre-helm because
every Secret below is named by an install-time value and mounted as a volume. A volume's
Secret has to exist before the pod is scheduled: unlike `valueFrom.secretKeyRef`, which
fails one container at a time, a missing volume Secret makes kubelet refuse to start the
whole pod with FailedMount. Creating these after install would wedge the pods.

Creates the operator-defined Secrets that configs/enable-secrets-from-files.yaml refers
to. The chart cannot create them -- they stand in for secrets a real operator supplies:

  - sff-houston-operator-secret   (token)  houston.secret[]   -> SFF_HOUSTON_EXTRA_SECRET
  - sff-navigator-operator-secret (token)  navigator.secret[] -> SFF_NAVIGATOR_EXTRA_SECRET
  - sff-dplink-operator-secret    (token)  dpLink.secret[]    -> SFF_DPLINK_EXTRA_SECRET
        These three exercise HOUSTON_SECRETS_FROM_FILES_EXTRA, the only mechanism for
        secrets whose env var names are not known at chart build time.
  - sff-es-credentials         (elastic)                      external-es-proxy esproxy lua
  - sff-aws-credentials        (aws_access_key, aws_secret_key) external-es-proxy awsproxy
        Mounted whole, so the key names ARE the filenames the shell preamble cats.
  - sff-es-basic-credentials   (username, password)           vector elasticsearch sink

Every value is a greppable dummy. These prove a delivery mechanism, so they only have to
be present and distinctive -- and distinctive matters: the scenario asserts that none of
these strings appears in any container's environment, which only works if each value is
unique enough to grep for unambiguously.

This creates Secrets in whatever cluster KUBECONFIG points at, so --namespace is REQUIRED
and has no default: running it bare (or to read --help) aborts before touching anything.
reset-local-dev exports KUBECONFIG at the fresh scenario cluster and puts kubectl on PATH.
"""

import argparse
import subprocess
import sys

# The marker every dummy value carries, so the scenario can assert in one grep that no
# fixture value reached a process environment, and so anything found in a real cluster is
# immediately identifiable as test scaffolding.
MARKER = "sff-not-a-real-secret"

# secret name -> {key: value}. Key names are load-bearing for the two mounted whole or
# mounted-by-key-name: see the module docstring.
FIXTURES: dict[str, dict[str, str]] = {
    "sff-houston-operator-secret": {"token": f"houston-extra-{MARKER}"},
    "sff-navigator-operator-secret": {"token": f"navigator-extra-{MARKER}"},
    "sff-dplink-operator-secret": {"token": f"dplink-extra-{MARKER}"},
    # The esproxy lua base64-encodes this into an Authorization: Basic header, so it has
    # to look like user:pass rather than an opaque blob.
    "sff-es-credentials": {"elastic": f"sff-es-user:es-{MARKER}"},
    "sff-aws-credentials": {
        "aws_access_key": f"AKIA-{MARKER}",
        "aws_secret_key": f"aws-secret-{MARKER}",
    },
    "sff-es-basic-credentials": {
        "username": "sff-vector-es-user",
        "password": f"vector-es-{MARKER}",
    },
}


def parse_args() -> argparse.Namespace:
    """Parse (and require) the target namespace, so a bare run cannot mutate a cluster."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--namespace",
        required=True,
        help="Namespace to create the fixture Secrets in (e.g. astronomer). Required on "
        "purpose: there is no default, so an accidental invocation touches nothing.",
    )
    return parser.parse_args()


def kubectl(*args: str) -> subprocess.CompletedProcess:
    """kubectl wrapper. KUBECONFIG comes from the environment reset-local-dev exports."""
    result = subprocess.run(["kubectl", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"ERROR: kubectl {' '.join(args)} failed:\n{result.stderr}")
    return result


def main() -> None:
    args = parse_args()
    namespace = args.namespace

    for name, data in FIXTURES.items():
        # Recreate rather than patch, so a re-run cannot leave a stale key behind from an
        # earlier revision of this file -- a leftover key is invisible until some assertion
        # reads the wrong one.
        subprocess.run(
            ["kubectl", "-n", namespace, "delete", "secret", name, "--ignore-not-found"],
            capture_output=True,
            text=True,
        )
        literals = [f"--from-literal={key}={value}" for key, value in data.items()]
        kubectl("-n", namespace, "create", "secret", "generic", name, *literals)
        print(f"  created secret {namespace}/{name} (keys: {', '.join(sorted(data))})")

    print(f"{len(FIXTURES)} secrets-from-files fixture Secrets ready in {namespace}.")


if __name__ == "__main__":
    sys.exit(main())
