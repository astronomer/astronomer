#!/usr/bin/env python3
"""
JWKS Fetcher for Astronomer Registry

This script fetches JWKS (JSON Web Key Set) from the control plane
and creates a Kubernetes secret for registry authentication.
"""

import base64
import json
import os
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def log(message):
    """Log with timestamp and prefix"""
    print(f"[JWKS-HOOK] {message}")
    sys.stdout.flush()


def validate_url_scheme(url):
    """Validate that URL uses HTTPS scheme for security"""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed. Only HTTP/HTTPS permitted.")
    return True


def fetch_jwks_from_endpoint():
    """Fetch JWKS from the control plane endpoint"""
    control_plane_endpoint = os.getenv("CONTROL_PLANE_ENDPOINT")
    jwks_url = f"{control_plane_endpoint}/.well-known/jwks.json"
    retry_attempts = int(os.getenv("RETRY_ATTEMPTS", "5"))
    retry_delay = int(os.getenv("RETRY_DELAY", "10"))

    log(f"Fetching JWKS from: {jwks_url}")

    validate_url_scheme(jwks_url)

    for attempt in range(1, retry_attempts + 1):
        log(f"Attempt {attempt} of {retry_attempts}")

        try:
            request = Request(jwks_url)  # noqa: S310 - URL scheme validated above
            request.add_header("Accept", "application/json")
            request.add_header("User-Agent", "Astronomer-Registry-JWKS-Hook/1.0")

            with urlopen(request, timeout=30) as response:  # noqa: S310 - URL scheme validated above
                if response.status == 200:
                    jwks_data = response.read().decode("utf-8")
                    log("Successfully fetched JWKS")
                    return json.loads(jwks_data)
                log(f"HTTP {response.status}: {response.reason}")

        except (URLError, HTTPError) as e:
            log(f"Network error: {e}")
        except json.JSONDecodeError as e:
            log(f"JSON decode error: {e}")
        except (ValueError, OSError) as e:
            log(f"Validation or system error: {e}")

        if attempt < retry_attempts:
            log(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)

    raise RuntimeError(f"Failed to fetch JWKS after {retry_attempts} attempts")


def validate_jwks_structure(jwks_data):
    """Validate the JWKS structure matches expected format"""
    if not isinstance(jwks_data, dict):
        raise ValueError("JWKS must be a JSON object")

    if "keys" not in jwks_data:
        raise ValueError("JWKS must contain 'keys' field")

    if not isinstance(jwks_data["keys"], list):
        raise ValueError("JWKS 'keys' must be an array")

    if len(jwks_data["keys"]) == 0:
        raise ValueError("JWKS 'keys' array cannot be empty")

    for i, key in enumerate(jwks_data["keys"]):
        required_fields = ["kty", "kid"]
        for field in required_fields:
            if field not in key:
                raise ValueError(f"Key {i} missing required field: {field}")

    log(f"JWKS validation successful - found {len(jwks_data['keys'])} keys")
    return True


def create_kubernetes_secret(jwks_data):
    """Create Kubernetes secret with JWKS data"""
    secret_name = os.getenv("SECRET_NAME", "registry-jwt-secret")
    namespace = os.getenv("NAMESPACE")
    release_name = os.getenv("RELEASE_NAME", "astronomer")

    log(f"Creating secret '{secret_name}' in namespace '{namespace}'")

    jwks_json = json.dumps(jwks_data, indent=2)

    try:
        result = subprocess.run(
            ["kubectl", "get", "secret", secret_name, "-n", namespace], capture_output=True, text=True, check=False
        )

        secret_exists = result.returncode == 0

        if secret_exists:
            log(f"Secret '{secret_name}' already exists, updating...")
            action = "apply"
        else:
            log(f"Creating new secret '{secret_name}'...")
            action = "apply"

        secret_yaml = f"""apiVersion: v1
kind: Secret
metadata:
  name: {secret_name}
  namespace: {namespace}
  labels:
    tier: astronomer
    component: registry
    release: {release_name}
    app.kubernetes.io/name: registry-jwks
    app.kubernetes.io/instance: {release_name}
    app.kubernetes.io/component: registry-jwks
  annotations:
    astronomer.io/commander-sync: "platform-release={release_name}"
    astronomer.io/jwks-source: "{os.getenv("CONTROL_PLANE_ENDPOINT")}/.well-known/jwks.json"
    astronomer.io/jwks-fetched-at: "{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}"
type: Opaque
data:
  tls.crt: {base64.b64encode(jwks_json.encode("utf-8")).decode("ascii")}
"""

        subprocess.run(["kubectl", action, "-f", "-"], input=secret_yaml, text=True, capture_output=True, check=True)

        log(f"Secret '{secret_name}' {action}d successfully")

        verify_result = subprocess.run(
            ["kubectl", "get", "secret", secret_name, "-n", namespace, "-o", "jsonpath={.metadata.labels.component}"],
            capture_output=True,
            text=True,
            check=True,
        )

        if verify_result.stdout.strip() == "registry":
            log("Secret verification successful")
        else:
            log("Warning: Secret verification failed")

    except subprocess.CalledProcessError as e:
        log(f"kubectl error: {e}")
        log(f"stdout: {e.stdout}")
        log(f"stderr: {e.stderr}")
        raise RuntimeError(f"Failed to create/update Kubernetes secret: {e}") from e


def main():
    """Main function"""
    log("Starting JWKS fetcher for registry authentication...")

    control_plane_endpoint = os.getenv("CONTROL_PLANE_ENDPOINT")
    namespace = os.getenv("NAMESPACE")
    release_name = os.getenv("RELEASE_NAME", "astronomer")

    if not control_plane_endpoint:
        log("Error: CONTROL_PLANE_ENDPOINT environment variable not set")
        sys.exit(1)

    if not namespace:
        log("Error: NAMESPACE environment variable not set")
        sys.exit(1)

    log("Configuration:")
    log(f"  Control Plane: {control_plane_endpoint}")
    log(f"  JWKS Endpoint: {control_plane_endpoint}/.well-known/jwks.json")
    log(f"  Target Secret: {os.getenv('SECRET_NAME', 'registry-jwt-secret')}")
    log(f"  Target Namespace: {namespace}")
    log(f"  Release Name: {release_name}")

    try:
        jwks_data = fetch_jwks_from_endpoint()

        validate_jwks_structure(jwks_data)

        create_kubernetes_secret(jwks_data)
        log("JWKS hook completed successfully!")
        log("Registry components can now use the 'registry-jwt-secret' for JWT validation")
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as e:
        log(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
