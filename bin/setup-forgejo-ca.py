#!/usr/bin/env python3
"""Pre-helm setup for the git-sync-private-ca scenario (PINF-1109).

Runs via test_profile.yaml's `pre_helm_scripts` -- i.e. after the cluster exists but
BEFORE `helm install` (see tests/functional/scenarios/README.md). It must run pre-helm
because the CA Secret it creates is referenced by install-time `global.privateCaCerts`,
which commander mounts (and runs update-ca-certificates over) at startup; a Secret
created after install wouldn't reach commander without a restart.

Generates a throwaway private CA + a Forgejo server cert (SAN = the in-cluster Forgejo
Service DNS), then creates:

  - Secret astronomer/forgejo-ca (key `cert.pem`) -- the CA the platform trusts. Listed
    in global.privateCaCerts so commander trusts it, and annotated for commander-sync so
    it is replicated into each Airflow Deployment namespace where git-sync-relay mounts
    it (via deployments.privateCaCertSecretNames -> global.privateCaCerts on the chart).
  - Secret git-forgejo/forgejo-tls (tls) -- the server cert Forgejo serves HTTPS with.
    The Forgejo Deployment (applied later by the test's fixture) mounts this.

KUBECONFIG is exported by reset-local-dev; kubectl and openssl are on PATH.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

# Shared identifiers. The scenario's test and forgejo.yaml manifest must agree with these.
PLATFORM_NAMESPACE = "astronomer"
FORGEJO_NAMESPACE = "git-forgejo"
FORGEJO_SERVICE = "forgejo"
FORGEJO_FQDN = f"{FORGEJO_SERVICE}.{FORGEJO_NAMESPACE}.svc.cluster.local"
CA_SECRET_NAME = "forgejo-ca"  # noqa: S105 -- k8s Secret name, not a credential
TLS_SECRET_NAME = "forgejo-tls"  # noqa: S105 -- k8s Secret name, not a credential
COMMANDER_SYNC_ANNOTATION = "astronomer.io/commander-sync"


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


def generate_certs(cert_dir: Path) -> tuple[Path, Path, Path]:
    """Generate a private CA and a Forgejo server cert signed by it. Returns (ca_crt, server_crt, server_key)."""
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
    run(["openssl", "req", "-new", "-key", str(server_key), "-subj", f"/CN={FORGEJO_FQDN}", "-out", str(server_csr)])
    san_ext.write_text(
        "basicConstraints=CA:FALSE\n"
        "keyUsage=digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        f"subjectAltName=DNS:{FORGEJO_FQDN},DNS:{FORGEJO_SERVICE}.{FORGEJO_NAMESPACE}.svc,"
        f"DNS:{FORGEJO_SERVICE}.{FORGEJO_NAMESPACE},DNS:{FORGEJO_SERVICE}\n"
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


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="forgejo-ca-") as tmp:
        ca_crt, server_crt, server_key = generate_certs(Path(tmp))

        # CA the platform trusts. The astronomer namespace already exists (setup-kind.py).
        # Key MUST be cert.pem -- the astronomer chart's custom_ca_volume_mounts and
        # git-sync-relay both mount the CA via `subPath: cert.pem`.
        kubectl("-n", PLATFORM_NAMESPACE, "delete", "secret", CA_SECRET_NAME, "--ignore-not-found", ignore_not_found=True)
        kubectl("-n", PLATFORM_NAMESPACE, "create", "secret", "generic", CA_SECRET_NAME, f"--from-file=cert.pem={ca_crt}")
        # commander-sync (matched by key only, value ignored) replicates it into deployment namespaces.
        kubectl("-n", PLATFORM_NAMESPACE, "annotate", "secret", CA_SECRET_NAME, f"{COMMANDER_SYNC_ANNOTATION}=", "--overwrite")

        # TLS cert Forgejo serves with, in its own namespace. `create namespace` isn't
        # idempotent, so render it and apply (apply is idempotent for local re-runs).
        ns_manifest = subprocess.run(
            ["kubectl", "create", "namespace", FORGEJO_NAMESPACE, "--dry-run=client", "-o=yaml"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        run(["kubectl", "apply", "-f", "-"], input=ns_manifest, text=True)
        kubectl("-n", FORGEJO_NAMESPACE, "delete", "secret", TLS_SECRET_NAME, "--ignore-not-found", ignore_not_found=True)
        kubectl("-n", FORGEJO_NAMESPACE, "create", "secret", "tls", TLS_SECRET_NAME, f"--cert={server_crt}", f"--key={server_key}")

    print(f"OK: created Secret {PLATFORM_NAMESPACE}/{CA_SECRET_NAME} and {FORGEJO_NAMESPACE}/{TLS_SECRET_NAME}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: forgejo CA setup failed: {e}", file=sys.stderr)
        raise SystemExit(1) from e
