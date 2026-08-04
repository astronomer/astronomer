#!/usr/bin/env python3
"""Pre-helm setup for the git-sync-private-ca scenario (PINF-1109).

Runs via test_profile.yaml's `pre_helm_scripts` -- i.e. after the cluster exists but
BEFORE `helm install` (see tests/functional/scenarios/README.md). It must run pre-helm
because the CA Secret it creates is referenced by install-time `global.privateCaCerts`,
which commander mounts (and runs update-ca-certificates over) at startup; a Secret
created after install wouldn't reach commander without a restart.

Generates a throwaway private CA + a Forgejo server cert (SAN = the in-cluster Forgejo
Service DNS), then creates, in the namespaces given on the command line:

  - Secret <platform-namespace>/forgejo-ca (key `cert.pem`) -- the CA the platform trusts.
    Listed in global.privateCaCerts so commander trusts it, and annotated for commander-sync
    so it is replicated into each Airflow Deployment namespace where git-sync-relay mounts it
    (via deployments.privateCaCertSecretNames -> global.privateCaCerts on the chart).
  - Secret <forgejo-namespace>/forgejo-tls (tls) -- the server cert Forgejo serves HTTPS with.
  - Secret <forgejo-namespace>/forgejo-untrusted-tls (tls) -- a self-signed cert whose CA is
    NEVER trusted, for the fail-closed cases (TC-CA-04, TC-CA-12).

This creates and deletes Secrets (and creates the Forgejo namespace) in whatever cluster
KUBECONFIG points at. The namespaces are REQUIRED and have no defaults, precisely so an
accidental invocation (e.g. running it to read `--help`) cannot mutate your current context:
with no arguments it aborts before touching the cluster. reset-local-dev exports KUBECONFIG
at the fresh scenario cluster and passes the namespaces; kubectl and openssl are on PATH.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

# Fixed identifiers. The scenario's test and forgejo.yaml manifest must agree with these; only
# the namespaces are variable (passed in), so an accidental run can't default to a real cluster.
FORGEJO_SERVICE = "forgejo"
UNTRUSTED_SERVICE = "forgejo-untrusted"
CA_SECRET_NAME = "forgejo-ca"  # noqa: S105 -- k8s Secret name, not a credential
TLS_SECRET_NAME = "forgejo-tls"  # noqa: S105 -- k8s Secret name, not a credential
UNTRUSTED_TLS_SECRET_NAME = "forgejo-untrusted-tls"  # noqa: S105 -- k8s Secret name, not a credential
COMMANDER_SYNC_ANNOTATION = "astronomer.io/commander-sync"


def parse_args() -> argparse.Namespace:
    """Parse (and require) the target namespaces. argparse gives `--help` and, because both
    namespaces are required with no defaults, aborts a bare/accidental invocation before any
    cluster mutation."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--platform-namespace",
        required=True,
        help="Namespace the Astronomer platform (and commander) is installed in; the "
        "commander-sync-annotated CA Secret is created here (e.g. astronomer).",
    )
    parser.add_argument(
        "--forgejo-namespace",
        required=True,
        help="Namespace for the in-cluster Forgejo host's TLS Secrets, created if absent (e.g. git-forgejo).",
    )
    return parser.parse_args()


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, echoing it, and fail loudly on non-zero exit."""
    print(f"+ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def kubectl(*args: str, ignore_not_found: bool = False) -> subprocess.CompletedProcess:
    """kubectl wrapper (KUBECONFIG comes from the environment set by reset-local-dev)."""
    cmd = ["kubectl", *args]
    if ignore_not_found:
        # For idempotent delete-before-create on local re-runs against a reused cluster.
        return subprocess.run(cmd)
    return run(cmd)


def generate_certs(cert_dir: Path, forgejo_namespace: str) -> tuple[Path, Path, Path]:
    """Generate a private CA and a Forgejo server cert signed by it (SAN = the Forgejo Service DNS
    in forgejo_namespace). Returns (ca_crt, server_crt, server_key)."""
    forgejo_fqdn = f"{FORGEJO_SERVICE}.{forgejo_namespace}.svc.cluster.local"
    ca_key, ca_crt = cert_dir / "ca.key", cert_dir / "ca.crt"
    server_key, server_csr, server_crt = cert_dir / "server.key", cert_dir / "server.csr", cert_dir / "server.crt"
    san_ext = cert_dir / "san.ext"

    run(["openssl", "genrsa", "-out", str(ca_key), "4096"])
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-new",
            "-nodes",
            "-key",
            str(ca_key),
            "-sha256",
            "-days",
            "3650",
            "-subj",
            "/CN=git-sync-private-ca test CA/O=astronomer-test",
            "-out",
            str(ca_crt),
        ]
    )

    run(["openssl", "genrsa", "-out", str(server_key), "2048"])
    run(["openssl", "req", "-new", "-key", str(server_key), "-subj", f"/CN={forgejo_fqdn}", "-out", str(server_csr)])
    san_ext.write_text(
        "basicConstraints=CA:FALSE\n"
        "keyUsage=digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        f"subjectAltName=DNS:{forgejo_fqdn},DNS:{FORGEJO_SERVICE}.{forgejo_namespace}.svc,"
        f"DNS:{FORGEJO_SERVICE}.{forgejo_namespace},DNS:{FORGEJO_SERVICE}\n"
    )
    run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(server_csr),
            "-CA",
            str(ca_crt),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-sha256",
            "-days",
            "825",
            "-extfile",
            str(san_ext),
            "-out",
            str(server_crt),
        ]
    )
    return ca_crt, server_crt, server_key


def generate_untrusted_cert(cert_dir: Path, forgejo_namespace: str) -> tuple[Path, Path]:
    """A self-signed cert for the untrusted host. Its (self-signed) CA is never added to
    global.privateCaCerts, so a relay/commander connecting to it fails TLS -- fails closed."""
    untrusted_fqdn = f"{UNTRUSTED_SERVICE}.{forgejo_namespace}.svc.cluster.local"
    key, crt = cert_dir / "untrusted.key", cert_dir / "untrusted.crt"
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "825",
            "-keyout",
            str(key),
            "-out",
            str(crt),
            "-subj",
            f"/CN={untrusted_fqdn}",
            "-addext",
            f"subjectAltName=DNS:{untrusted_fqdn}",
        ]
    )
    return crt, key


def main() -> None:
    args = parse_args()
    platform_namespace, forgejo_namespace = args.platform_namespace, args.forgejo_namespace

    with tempfile.TemporaryDirectory(prefix="forgejo-ca-") as tmp:
        ca_crt, server_crt, server_key = generate_certs(Path(tmp), forgejo_namespace)

        # CA the platform trusts. The platform namespace already exists (setup-kind.py).
        # Key MUST be cert.pem -- the astronomer chart's custom_ca_volume_mounts and
        # git-sync-relay both mount the CA via `subPath: cert.pem`.
        kubectl("-n", platform_namespace, "delete", "secret", CA_SECRET_NAME, "--ignore-not-found", ignore_not_found=True)
        kubectl("-n", platform_namespace, "create", "secret", "generic", CA_SECRET_NAME, f"--from-file=cert.pem={ca_crt}")
        # commander-sync (matched by key only, value ignored) replicates it into deployment namespaces.
        kubectl("-n", platform_namespace, "annotate", "secret", CA_SECRET_NAME, f"{COMMANDER_SYNC_ANNOTATION}=", "--overwrite")

        # TLS cert Forgejo serves with, in its own namespace. `create namespace` isn't
        # idempotent, so render it and apply (apply is idempotent for local re-runs).
        ns_manifest = subprocess.run(
            ["kubectl", "create", "namespace", forgejo_namespace, "--dry-run=client", "-o=yaml"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        run(["kubectl", "apply", "-f", "-"], input=ns_manifest, text=True)
        kubectl("-n", forgejo_namespace, "delete", "secret", TLS_SECRET_NAME, "--ignore-not-found", ignore_not_found=True)
        kubectl("-n", forgejo_namespace, "create", "secret", "tls", TLS_SECRET_NAME, f"--cert={server_crt}", f"--key={server_key}")

        # Untrusted host's TLS (self-signed, CA never trusted) -- for the fail-closed cases.
        untrusted_crt, untrusted_key = generate_untrusted_cert(Path(tmp), forgejo_namespace)
        kubectl("-n", forgejo_namespace, "delete", "secret", UNTRUSTED_TLS_SECRET_NAME, "--ignore-not-found", ignore_not_found=True)
        kubectl(
            "-n",
            forgejo_namespace,
            "create",
            "secret",
            "tls",
            UNTRUSTED_TLS_SECRET_NAME,
            f"--cert={untrusted_crt}",
            f"--key={untrusted_key}",
        )

    print(
        f"OK: created {platform_namespace}/{CA_SECRET_NAME}, {forgejo_namespace}/{TLS_SECRET_NAME}, "
        f"and {forgejo_namespace}/{UNTRUSTED_TLS_SECRET_NAME}"
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: forgejo CA setup failed: {e}", file=sys.stderr)
        raise SystemExit(1) from e
