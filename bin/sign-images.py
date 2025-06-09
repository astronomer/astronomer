#!/usr/bin/env python3
"""
Script to sign all container images in the Astronomer release JSON using cosign.
"""

import argparse
import base64
import getpass
import json
import os
import subprocess
import sys
import tempfile

import requests


def check_requirements():
    """Check if required tools are installed."""
    # Check for cosign
    try:
        subprocess.run(["which", "cosign"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("Error: cosign is not installed. Please install it first.")
        print("Visit https://github.com/sigstore/cosign for installation instructions.")
        sys.exit(1)
    try:
        import importlib.util

        if importlib.util.find_spec("requests") is None:
            print("Error: Python 'requests' module is not installed.")
            print("Install it using: pip install requests")
            sys.exit(1)
    except ImportError:
        print("Error: Python 'requests' module is not installed.")
        print("Install it using: pip install requests")
        sys.exit(1)


def write_key_file(env_var_name, file_path):
    """Write a base64-encoded key from environment variable to a file."""
    encoded_key = os.environ.get(env_var_name)
    if not encoded_key:
        print(f"Error: Environment variable {env_var_name} not found.")
        sys.exit(1)
    try:
        decoded_key = base64.b64decode(encoded_key)
        with open(file_path, "wb") as key_file:
            key_file.write(decoded_key)
        os.chmod(file_path, 0o600)  # Set secure permissions
        return True
    except (base64.binascii.Error, OSError) as e:
        print(f"Error decoding or writing key from {env_var_name}: {e}")
        sys.exit(1)


def sign_image(repo, tag, sha, key_path, password=None):
    """Sign a container image with cosign."""
    full_image = f"{repo}:{tag}"
    digest_reference = f"{full_image}@sha256:{sha}"

    print(f"Signing image: {full_image} with SHA: {sha}")
    env = os.environ.copy()
    if password:
        env["COSIGN_PASSWORD"] = password

    try:
        subprocess.run(
            ["cosign", "verify", "--key", f"{key_path}.pub", "--insecure-ignore-tlog", digest_reference],
            check=True,
            capture_output=True,
        )
        print(f"Image already signed: {full_image}")
        return  # Skip if already signed
    except subprocess.CalledProcessError:
        pass  # Image is not yet signed

    sign_cmd = ["cosign", "sign", "--key", key_path, "--tlog-upload=false", digest_reference]
    try:
        subprocess.run(sign_cmd, env=env, check=True)
        print(f"✓ Signed {full_image}")
    except subprocess.CalledProcessError as e:
        print(f"Error signing {full_image}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Sign container images in an Astronomer release.")
    parser.add_argument("--version", "-v", help="Version tag to sign (e.g., 0.36.0)", required=False)
    args = parser.parse_args()

    check_requirements()

    # Creating temporary directory for key files
    with tempfile.TemporaryDirectory() as temp_dir:
        private_key_path = os.path.join(temp_dir, "cosign.key")
        public_key_path = os.path.join(temp_dir, "cosign.key.pub")

        print("Writing private key to temporary file...")
        write_key_file("COSIGN_PRIVATE_KEY", private_key_path)

        print("Writing public key to temporary file...")
        write_key_file("COSIGN_PUBLIC_KEY", public_key_path)

        password = os.environ.get("COSIGN_PASSWORD")
        if not password:
            password = getpass.getpass("Enter password for cosign key: ")

        version = args.version
        if not version:
            version = os.environ.get("IMAGE_TAG")
            if not version:
                # If tag starts with 'v', remove it
                if os.environ.get("NEXT_TAG") and os.environ.get("NEXT_TAG").startswith("v"):
                    version = os.environ.get("NEXT_TAG")[1:]
                else:
                    version = os.environ.get("NEXT_TAG") or os.environ.get("IMG_TAG")

        if not version:
            print("Error: No version specified. Use --version or set IMAGE_TAG/NEXT_TAG/IMG_TAG environment variable.")
            sys.exit(1)

        print(f"Signing images for version: {version}")

        json_url = f"https://updates.astronomer.io/astronomer-software/releases/astronomer-{version}.json"
        try:
            print(f"Fetching data from {json_url}...")
            response = requests.get(json_url, timeout=100)
            response.raise_for_status()
            data = response.json()
            print("Successfully fetched data from URL")
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"Failed to fetch data from URL: {e}")
            print("Falling back to local file...")
            json_file = f"astronomer-{version}.json"
            try:
                with open(json_file) as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                print(f"Error: Could not find or parse local file {json_file}")
                sys.exit(1)
        print("Signing Astronomer images...")
        for image_data in data["astronomer"]["images"].values():
            sign_image(image_data["repository"], image_data["tag"], image_data["sha256"], private_key_path, password)

        print("All images have been processed.")


if __name__ == "__main__":
    main()
