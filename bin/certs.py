#!/usr/bin/env python3
"""Create and validate certificates for Astronomer Software functional tests."""

import argparse
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.backends import default_backend

cert_dir = Path.home() / ".local" / "share" / "astronomer-software" / "certs"
cert_dir.mkdir(parents=True, exist_ok=True)
astronomer_tls_cert_file = cert_dir / "astronomer-tls.pem"
astronomer_tls_key_file = cert_dir / "astronomer-tls.key"
astronomer_private_ca_cert_file = cert_dir / "astronomer-private-ca.pem"
astronomer_private_ca_key_file = cert_dir / "astronomer-private-ca.key"
MKCERT_EXE = str(Path.home() / ".local" / "share" / "astronomer-software" / "bin" / "mkcert")


def validate_certificate(cert_path):
    """
    Validate the certificate and check its expiration.

    Args:
        cert_path: Path to the certificate file

    Returns:
        tuple: (bool, str) - (is_valid, message)
    """
    try:
        with open(cert_path, "rb") as f:
            cert_data = f.read()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

            # Check expiration
            now = datetime.now(UTC)

            if now > cert.not_valid_after_utc:
                return False, f"Certificate expired on {cert.not_valid_after_utc}"
            if now < cert.not_valid_before_utc:
                return False, f"Certificate not valid until {cert.not_valid_before_utc}"

            return True, "Certificate is valid"
    except Exception as e:  # noqa: BLE001
        return False, f"Certificate validation failed: {e}"


def cleanup_old_certificates(cert_dir=cert_dir):
    """
    Remove certificates that are expired or will expire within 4 weeks.
    Creates the certificate directory if it doesn't exist.
    """
    if not cert_dir.exists():
        cert_dir.mkdir(parents=True, exist_ok=True)
        return

    cert_files = [
        (astronomer_tls_cert_file, astronomer_tls_key_file),
        (astronomer_private_ca_cert_file, astronomer_private_ca_key_file),
    ]

    now = datetime.now(UTC)
    four_weeks = now + timedelta(weeks=4)

    for cert_file, key_file in cert_files:
        if cert_file.exists():
            try:
                with open(cert_file, "rb") as f:
                    cert_data = f.read()
                    cert = x509.load_pem_x509_certificate(cert_data, default_backend())

                    if cert.not_valid_after_utc <= four_weeks:
                        # Delete both cert and key if expired or expiring within 4 weeks
                        cert_file.unlink(missing_ok=True)
                        print(f"Removed expiring certificate: {cert_file}")
                        key_file.unlink(missing_ok=True)
                        print(f"Removed corresponding key file: {key_file}")
            except Exception:  # noqa: BLE001
                # If we can't read/parse the cert, remove it to be safe
                cert_file.unlink(missing_ok=True)
                print(f"Removed invalid certificate: {cert_file}")
                key_file.unlink(missing_ok=True)
                print(f"Removed corresponding key file: {key_file}")

    # Create directory if it was deleted
    cert_dir.mkdir(parents=True, exist_ok=True)


def create_astronomer_tls_certificates():
    """Use mkcert to create the certificate and key for the astronomer-tls secret.

    We use mkcert because it integrates with the system's trust store, allowing
    browsers to trust the generated certificates. This is useful for local
    development and testing, and because it makes this whole process easy.
    """

    domain = "localtest.me"  # localtest.me and *.localtest.me resolve to 127.0.0.1 using any DNS server

    if astronomer_tls_key_file.exists() and astronomer_tls_cert_file.exists():
        print("Using existing astronomer-tls certificates")
        return

    # Install the mkcert CA, then generate a wildcard cert and key.
    subprocess.run([MKCERT_EXE, "-install"], check=True)
    subprocess.run(
        [MKCERT_EXE, f"-cert-file={astronomer_tls_cert_file}", f"-key-file={astronomer_tls_key_file}", domain, f"*.{domain}"],
        check=True,
    )

    ca_root = subprocess.check_output([MKCERT_EXE, "-CAROOT"], text=True).strip()
    ca_root_pem = Path(ca_root) / "rootCA.pem"

    # Error checking
    if not astronomer_tls_cert_file.exists():
        raise FileNotFoundError(f"Certificate file not found: {astronomer_tls_cert_file}")
    if not astronomer_tls_key_file.exists():
        raise FileNotFoundError(f"Key file not found: {astronomer_tls_key_file}")
    if not ca_root_pem.exists():
        raise FileNotFoundError(f"CA root PEM file not found: {ca_root_pem}")

    # Append the CA root PEM to the cert file so we have a full chain
    with astronomer_tls_cert_file.open("ab") as out_f, ca_root_pem.open("rb") as ca_f:
        shutil.copyfileobj(ca_f, out_f)

    # Validate the generated certificate
    is_valid, message = validate_certificate(astronomer_tls_cert_file)
    if not is_valid:
        raise RuntimeError(f"Generated certificate is invalid: {message}")

    print(f"astronomer-tls certificate and key generated:\n  Cert: {astronomer_tls_cert_file}\n  Key: {astronomer_tls_key_file}")


def create_astronomer_private_ca_certificates():
    """Use mkcert to create the certificate and key for the astronomer-private-ca secret.

    We use mkcert because it integrates with the system's trust store, allowing
    browsers to trust the generated certificates. This is useful for local
    development and testing, and because it makes this whole process easy.
    """

    cert_dir = Path.home() / ".local" / "share" / "astronomer-software" / "certs"
    astronomer_private_ca_cert_file = cert_dir / "astronomer-private-ca.pem"
    astronomer_private_ca_key_file = cert_dir / "astronomer-private-ca.key"
    ca_root = subprocess.check_output([MKCERT_EXE, "-CAROOT"], text=True).strip()
    ca_root_pem = Path(ca_root) / "rootCA.pem"

    # Clean up old certificates
    cleanup_old_certificates(cert_dir)

    if astronomer_private_ca_key_file.exists() and astronomer_private_ca_cert_file.exists():
        print("Using existing astronomer-private-ca certificates")
        return

    # Generate the private CA certificate and key.
    subprocess.run(
        [
            MKCERT_EXE,
            f"-cert-file={astronomer_private_ca_cert_file}",
            f"-key-file={astronomer_private_ca_key_file}",
            "server.example.org",
        ],
        check=True,
    )

    # Error checking
    if not astronomer_private_ca_cert_file.exists():
        raise FileNotFoundError(f"Certificate file not found: {astronomer_private_ca_cert_file}")
    if not astronomer_private_ca_key_file.exists():
        raise FileNotFoundError(f"Key file not found: {astronomer_private_ca_key_file}")
    if not ca_root_pem.exists():
        raise FileNotFoundError(f"CA root PEM file not found: {ca_root_pem}")

    # Validate the generated certificate
    is_valid, message = validate_certificate(astronomer_private_ca_cert_file)
    if not is_valid:
        raise RuntimeError(f"Generated certificate is invalid: {message}")

    print(f"Certificate and key generated:\n  Cert: {astronomer_private_ca_cert_file}\n  Key: {astronomer_private_ca_key_file}")


def main():
    parser = argparse.ArgumentParser(description="Astronomer Software Certificate Manager using mkcert")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Action to perform")

    subparsers.add_parser("cleanup", help="Remove expiring certificates")
    subparsers.add_parser("generate-tls", help="Create astronomer-tls certificates")
    subparsers.add_parser("generate-private-ca", help="Create astronomer-private-ca certificates")
    validate_parser = subparsers.add_parser("validate", help="Validate a certificate")
    validate_parser.add_argument("cert_path", type=str, help="Path to the certificate file")

    args = parser.parse_args()

    match args.command:
        case "cleanup":
            cleanup_old_certificates(cert_dir)
        case "generate-tls":
            create_astronomer_tls_certificates()
        case "generate-private-ca":
            create_astronomer_private_ca_certificates()
        case "validate":
            path = Path(args.cert_path)
            is_valid, message = validate_certificate(path)
            print(message)
            raise SystemExit(0 if is_valid else 1)
        case _:
            parser.print_help()


if __name__ == "__main__":
    main()
