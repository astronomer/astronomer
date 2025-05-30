import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from tests.utils.install_ci_tools import install_mkcert

cert_dir = Path.home() / ".local" / "share" / "astronomer-software" / "certs"
astronomer_tls_cert_file = cert_dir / "astronomer-tls.pem"
astronomer_tls_key_file = cert_dir / "astronomer-tls.key"
astronomer_private_ca_cert_file = cert_dir / "astronomer-private-ca.pem"
astronomer_private_ca_key_file = cert_dir / "astronomer-private-ca.key"


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
                        key_file.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                # If we can't read/parse the cert, remove it to be safe
                cert_file.unlink(missing_ok=True)
                key_file.unlink(missing_ok=True)

    # Create directory if it was deleted
    cert_dir.mkdir(parents=True, exist_ok=True)


def create_astronomer_tls_certificates():
    """Use mkcert to create the certificate and key for the astronomer-tls secret.

    We use mkcert because it integrates with the system's trust store, allowing
    browsers to trust the generated certificates. This is useful for local
    development and testing, and because it makes this whole process easy.
    """

    domain = "localtest.me"  # localtest.me resolves to 127.0.0.1 using any DNS server

    # Verify mkcert is installed
    install_mkcert()

    # Clean up old certificates
    cleanup_old_certificates(cert_dir)

    # Install the mkcert CA, then generate a wildcard cert and key.
    subprocess.run(["mkcert", "-install"], check=True)
    subprocess.run(
        ["mkcert", f"-cert-file={astronomer_tls_cert_file}", f"-key-file={astronomer_tls_key_file}", domain, f"*.{domain}"],
        check=True,
    )

    ca_root = subprocess.check_output(["mkcert", "-CAROOT"], text=True).strip()
    ca_root_pem = Path(ca_root) / "rootCA.pem"

    # Error checking
    if not astronomer_tls_cert_file.exists():
        raise FileNotFoundError(f"Certificate file not found: {astronomer_tls_cert_file}")
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
    ca_root = subprocess.check_output(["mkcert", "-CAROOT"], text=True).strip()
    ca_root_pem = Path(ca_root) / "rootCA.pem"

    # Verify mkcert is installed
    install_mkcert()

    # Clean up old certificates
    cleanup_old_certificates(cert_dir)

    # Generate the private CA certificate and key.
    subprocess.run(
        [
            "mkcert",
            f"-cert-file={astronomer_private_ca_cert_file}",
            f"-key-file={astronomer_private_ca_key_file}",
            "server.example.org",
        ],
        check=True,
    )

    # Error checking
    if not astronomer_private_ca_cert_file.exists():
        raise FileNotFoundError(f"Certificate file not found: {astronomer_private_ca_cert_file}")
    if not ca_root_pem.exists():
        raise FileNotFoundError(f"CA root PEM file not found: {ca_root_pem}")

    # Validate the generated certificate
    is_valid, message = validate_certificate(astronomer_private_ca_cert_file)
    if not is_valid:
        raise RuntimeError(f"Generated certificate is invalid: {message}")

    print(f"Certificate and key generated:\n  Cert: {astronomer_private_ca_cert_file}\n  Key: {astronomer_private_ca_key_file}")
