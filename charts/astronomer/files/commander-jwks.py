#!/usr/bin/env python3
"""
JWKS Fetcher for Astronomer Registry

This script fetches JWKS (JSON Web Key Set) from the control plane
and creates a Kubernetes secret for registry authentication.
"""

import base64
import json
import logging
import os
import subprocess
import sys
import textwrap
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cryptography import x509
from cryptography.hazmat.backends import default_backend


def setup_logger():
    """Setup logger with timestamp and prefix"""
    logger = logging.getLogger("JWKS-HOOK")
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    formatter = logging.Formatter("[JWKS-HOOK] %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


logger = setup_logger()


def validate_url_scheme(url):
    """Validate that URL uses HTTPS scheme for security"""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed. Only HTTP/HTTPS permitted.")
    return True


def fetch_jwks_from_endpoint(endpoint, retry_attempts, retry_delay):
    """Fetch JWKS from the control plane endpoint"""
    control_plane_endpoint = endpoint
    jwks_url = f"{control_plane_endpoint}/v1/.well-known/jwks.json"

    logger.info(f"Fetching JWKS from: {jwks_url}")

    validate_url_scheme(jwks_url)

    for attempt in range(1, retry_attempts + 1):
        logger.info(f"Attempt {attempt} of {retry_attempts}")

        try:
            request = Request(jwks_url)  # noqa: S310 - URL scheme validated above
            request.add_header("Accept", "application/json")
            request.add_header("User-Agent", "Astronomer-Registry-JWKS-Hook/1.0")

            with urlopen(request, timeout=30) as response:  # noqa: S310 - URL scheme validated above
                if response.status == 200:
                    jwks_data = response.read().decode("utf-8")
                    logger.info("Successfully fetched JWKS")
                    return json.loads(jwks_data)
                logger.warning(f"HTTP {response.status}: {response.reason}")

        except (URLError, HTTPError) as e:
            logger.error(f"Network error: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
        except (ValueError, OSError) as e:
            logger.error(f"Validation or system error: {e}")

        if attempt < retry_attempts:
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)

    raise RuntimeError(f"Failed to fetch JWKS after {retry_attempts} attempts")


def validate_jwks_structure(jwks_data):
    """Validate the JWKS structure matches expected format"""
    if not isinstance(jwks_data, dict):
        raise ValueError("JWKS response must be a JSON object")

    if "kty" not in jwks_data:
        raise ValueError("Key object must contain 'kty' field")

    logger.info("JWKS validation successful - found 1 key, converting to standard JWKS format")

    single_key = jwks_data.copy()
    jwks_data.clear()
    jwks_data["keys"] = [single_key]

    return True


def create_kubernetes_secret(jwks_data, endpoint, namespace, release_name, secret_name):
    """Create Kubernetes secret with JWKS data"""

    logger.info(f"Creating secret '{secret_name}' in namespace '{namespace}'")

    try:
        result = subprocess.run(
            ["kubectl", "get", "secret", secret_name, "-n", namespace], capture_output=True, text=True, check=False
        )

        secret_exists = result.returncode == 0
        action = "apply" if secret_exists else "create"
        logger.info(f"{'Updating' if secret_exists else 'Creating'} secret '{secret_name}'")

        secret_yaml = f"""apiVersion: v1
kind: Secret
metadata:
  name: {secret_name}
  namespace: {namespace}
  labels:
    tier: astronomer
    component: commander-jwks-hook
    release: {release_name}
    app.kubernetes.io/name: commander-jwks
    app.kubernetes.io/instance: {release_name}
    app.kubernetes.io/component: commander-jwks
  annotations:
    astronomer.io/commander-sync: "platform-release={release_name}"
    astronomer.io/jwks-source: "{endpoint}/v1/.well-known/jwks.json"
    astronomer.io/jwks-fetched-at: "{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}"
type: Opaque
data:
  tls.crt: {jwks_data}
"""

        subprocess.run(["kubectl", action, "-f", "-"], input=secret_yaml, text=True, capture_output=True, check=True)

        logger.info(f"Secret '{secret_name}' {action}d successfully")

        verify_result = subprocess.run(
            ["kubectl", "get", "secret", secret_name, "-n", namespace, "-o", "jsonpath={.metadata.labels.component}"],
            capture_output=True,
            text=True,
            check=True,
        )

        if verify_result.stdout.strip() == "commander-jwks-hook":
            logger.info("Secret verification successful")
        else:
            logger.warning("Warning: Secret verification failed")

    except subprocess.CalledProcessError as e:
        logger.error(f"kubectl error: {e}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        raise RuntimeError(f"Failed to create/update Kubernetes secret: {e}") from e


def get_base64_pem_from_jwks(jwks_data):
    cert_b64 = jwks_data["x5c"][0]
    pem = "-----BEGIN CERTIFICATE-----\n" + "\n".join(textwrap.wrap(cert_b64, 64)) + "\n-----END CERTIFICATE-----\n"
    return base64.b64encode(pem.encode()).decode()


def main():
    """Main function"""
    logger.info("Starting JWKS fetcher for registry authentication...")

    control_plane_endpoint = os.getenv("CONTROL_PLANE_ENDPOINT")
    namespace = os.getenv("NAMESPACE")
    release_name = os.getenv("RELEASE_NAME", "astronomer")
    secret_name = os.getenv("SECRET_NAME", f"{release_name}-commander-jwt-secret")
    retry_attempts = int(os.getenv("RETRY_ATTEMPTS", "5"))
    retry_delay = int(os.getenv("RETRY_DELAY", "10"))

    if not control_plane_endpoint:
        logger.error("Error: CONTROL_PLANE_ENDPOINT environment variable not set")
        sys.exit(1)

    if not namespace:
        logger.error("Error: NAMESPACE environment variable not set")
        sys.exit(1)

    logger.info("Configuration:")
    logger.info(f"  Control Plane: {control_plane_endpoint}")
    logger.info(f"  JWKS Endpoint: {control_plane_endpoint}/v1/.well-known/jwks.json")
    logger.info(f"  Target Secret: {secret_name}")
    logger.info(f"  Target Namespace: {namespace}")
    logger.info(f"  Release Name: {release_name}")

    try:
        jwks_data = fetch_jwks_from_endpoint(control_plane_endpoint, retry_attempts, retry_delay)
        signed_public_cert = get_base64_pem_from_jwks(jwks_data)
        logger.info(f"  Release Name: {release_name}")
        validate_jwks_structure(jwks_data)

        create_kubernetes_secret(signed_public_cert, control_plane_endpoint, namespace, release_name, secret_name)
        logger.info("JWKS hook completed successfully!")
        logger.info("Registry components can now use the 'commander-jwt-secret' for JWT validation")
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
