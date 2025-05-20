import shutil
import subprocess
from pathlib import Path

cert_dir = Path.home() / ".local" / "share" / "astronomer-software" / "certs"
cert_file = cert_dir / "fullchain.pem"
key_file = cert_dir / "privkey.pem"
domain = "localtest.me"  # localtest.me resolves to 127.0.0.1 using any DNS server


def create_certificates(cert_dir=cert_dir, cert_file=cert_file, key_file=key_file, domain=domain):
    """Use mkcert to create a self-signed certificate and key for local development.

    We use mkcert because it integrates with the system's trust store, allowing
    browsers to trust the generated certificates. This is useful for local
    development and testing, and because it makes this whole process easy.

    Args:
        cert_dir: Directory to store the cert and key files.
        cert_file: Path to the certificate file.
        key_file: Path to the private key file.
        domain: The base domain for the certificate. This will be the baseDomain for helm installation.
    """

    # Create cert_dir if it doesn't exist
    cert_dir.mkdir(parents=True, exist_ok=True)

    # Install the mkcert CA, then generate a wildcard cert and key.
    subprocess.run(["mkcert", "-install"], check=True)
    subprocess.run(["mkcert", "-cert-file", str(cert_file), "-key-file", str(key_file), domain, f"*.{domain}"], check=True)

    caroot = subprocess.check_output(["mkcert", "-CAROOT"], text=True).strip()
    ca_pem = Path(caroot) / "rootCA.pem"

    # Error checking
    if not cert_file.exists():
        raise FileNotFoundError(f"Certificate file not found: {cert_file}")
    if not ca_pem.exists():
        raise FileNotFoundError(f"CA root PEM file not found: {ca_pem}")

    # Append the CA root PEM to the cert file so we have a full chain
    with cert_file.open("ab") as out_f, ca_pem.open("rb") as ca_f:
        shutil.copyfileobj(ca_f, out_f)

    print(f"Certificate and key generated:\n  Cert: {cert_file}\n  Key: {key_file}")
