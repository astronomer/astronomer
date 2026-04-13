#!/usr/bin/env python3
"""Update containerd configuration to trust private CA certificates.

This script is deployed as a DaemonSet on every node and continuously monitors
for CA certificate changes, updating the containerd configuration accordingly.

Behaviour by containerd version (auto-detected via `containerd --version`):

  containerd 1.x (GKE <= 1.32):
    - Plugin namespace: io.containerd.grpc.v1.cri
    - If config_path is already set in config.toml under the correct plugin
      namespace, uses the certs.d/hosts.toml approach (no restart on cert updates).
    - If config_path is NOT set, falls back to inline config.toml modification
      and restarts containerd on every cert change.

  containerd 2.x (GKE >= 1.33):
    - Plugin namespace: io.containerd.cri.v1.images
    - Always uses the certs.d/hosts.toml approach.
    - If config_path is not already set in config.toml, injects it under the
      correct plugin namespace and restarts containerd ONCE on first setup.
    - Subsequent cert rotations update hosts.toml only (no restart).

Environment variables (injected by the Helm daemonset):
  REGISTRY_HOST         - Registry hostname (e.g. registry.example.com)
  CONTAINERD_HOST_PATH  - Host path to containerd config dir (default: /etc/containerd)
  CERT_CONFIG_PATH      - Host path to containerd certs.d dir (default: /etc/containerd/certs.d)
  PRIVATE_CA_CERTS_DIR  - Path to mounted CA cert secrets (default: /private-ca-certs)

Requires: Python >= 3.8 (available on GKE nodes).
"""

import hashlib
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("update-containerd-certs")

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
REGISTRY_HOST = os.environ.get("REGISTRY_HOST", "")
CONTAINERD_HOST_PATH = Path(os.environ.get("CONTAINERD_HOST_PATH", "/hostcontainerd"))
CERT_CONFIG_PATH = os.environ.get("CERT_CONFIG_PATH", "/etc/containerd/certs.d")
PRIVATE_CA_CERTS_DIR = Path(os.environ.get("PRIVATE_CA_CERTS_DIR", "/private-ca-certs"))

CONFIG_TOML = CONTAINERD_HOST_PATH / "config.toml"
CONFIG_TOML_BAK = CONTAINERD_HOST_PATH / "config.toml.bak"
CERTS_DIR = CONTAINERD_HOST_PATH / "certs.d" / REGISTRY_HOST

# Plugin namespaces per containerd major version
PLUGIN_NS = {
    1: 'plugins."io.containerd.grpc.v1.cri".registry',
    2: 'plugins."io.containerd.cri.v1.images".registry',
}

POLL_INTERVAL_SECONDS = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def detect_containerd_version() -> int:
    """Detect the major version of containerd running on the host.

    Uses nsenter to run `containerd --version` in the host PID namespace.
    Returns 1 or 2. Defaults to 2 if detection fails.
    """
    try:
        result = subprocess.run(
            ["nsenter", "--target", "1", "--mount", "--uts", "--ipc", "--net", "--pid", "containerd", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version_output = result.stdout.strip()
        log.info("containerd version output: %s", version_output)

        # Example outputs:
        #   containerd github.com/containerd/containerd 1.7.29 ...
        #   containerd github.com/containerd/containerd/v2 2.0.7 ...
        for token in version_output.split():
            if token and token[0].isdigit():
                major = int(token.split(".")[0])
                if major in (1, 2):
                    log.info("Detected containerd major version: %d", major)
                    return major
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as exc:
        log.warning("Failed to detect containerd version: %s", exc)

    log.warning("Defaulting to containerd version 2")
    return 2


def checksum_of_files(*paths: Path) -> str:
    """Return a combined SHA-256 hex digest of the given file contents."""
    h = hashlib.sha256()
    for p in sorted(paths):
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def restart_containerd() -> None:
    """Restart the containerd service on the host via nsenter."""
    log.info("Restarting containerd on host...")
    subprocess.run(
        ["nsenter", "--target", "1", "--mount", "--uts", "--ipc", "--net", "--pid", "systemctl", "restart", "containerd"],
        check=True,
        timeout=60,
    )
    log.info("containerd restarted.")


def backup_config_toml() -> None:
    """Create a timestamped backup of config.toml, and a stable .bak reference."""
    epoch = int(time.time())
    timestamped = CONTAINERD_HOST_PATH / f"config.toml.bak.{epoch}"
    shutil.copy2(CONFIG_TOML, timestamped)
    log.info("Created timestamped backup: %s", timestamped)

    if not CONFIG_TOML_BAK.is_file():
        shutil.copy2(CONFIG_TOML, CONFIG_TOML_BAK)
        log.info("Created stable backup: %s", CONFIG_TOML_BAK)


def config_path_is_set(config_text: str) -> bool:
    """Check if config_path is set anywhere in the config.toml content."""
    return "config_path" in config_text


def inject_config_path(containerd_version: int) -> None:
    """Add config_path to config.toml under the correct plugin namespace.

    This triggers a one-time containerd restart.
    """
    plugin_ns = PLUGIN_NS[containerd_version]
    stanza = f'\n[{plugin_ns}]\n  config_path = "{CERT_CONFIG_PATH}"\n'

    content = CONFIG_TOML_BAK.read_text()
    content += stanza

    CONFIG_TOML.write_text(content)
    log.info("Injected config_path under [%s]", plugin_ns)
    restart_containerd()


def generate_hosts_toml() -> str:
    """Generate a hosts.toml file for the registry with CA trust."""
    ca_path = CERTS_DIR / "ca.crt"
    return (
        f'server = "https://{REGISTRY_HOST}"\n'
        f"\n"
        f'[host."https://{REGISTRY_HOST}"]\n'
        f'  capabilities = ["pull", "resolve"]\n'
        f'  ca = ["{ca_path}"]\n'
    )


def copy_ca_certs() -> None:
    """Copy CA certificate PEM files from mounted secrets into the certs.d directory."""
    if not PRIVATE_CA_CERTS_DIR.is_dir():
        return

    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    ca_dest = CERTS_DIR / "ca.crt"

    for secret_dir in PRIVATE_CA_CERTS_DIR.iterdir():
        if not secret_dir.is_dir():
            continue
        for pem_file in secret_dir.glob("*.pem"):
            shutil.copy2(pem_file, ca_dest)
            log.info("Copied %s -> %s", pem_file, ca_dest)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    if not REGISTRY_HOST:
        log.error("REGISTRY_HOST environment variable is required")
        sys.exit(1)

    if not CONFIG_TOML.is_file():
        log.error("No %s found. Is this a containerd node?", CONFIG_TOML)
        sys.exit(1)

    backup_config_toml()

    containerd_version = detect_containerd_version()
    log.info("Using containerd version %d strategy", containerd_version)

    config_text = CONFIG_TOML.read_text()
    has_config_path = config_path_is_set(config_text)

    # For containerd 2.x: ensure config_path is set so certs.d/hosts.toml works
    if containerd_version == 2 and not has_config_path:
        log.info("config_path not found in config.toml, injecting...")
        inject_config_path(containerd_version)
        has_config_path = True

    # For containerd 1.x with config_path already set: use hosts.toml too
    use_hosts_toml = has_config_path

    if use_hosts_toml:
        log.info("Using certs.d/hosts.toml approach (no restarts on cert changes)")
    else:
        log.info("Using legacy inline config.toml approach (containerd 1.x fallback)")

    last_checksum = ""

    while True:
        copy_ca_certs()

        if use_hosts_toml:
            # --- hosts.toml path ---
            hosts_content = generate_hosts_toml()
            hosts_toml_path = CERTS_DIR / "hosts.toml"
            ca_crt_path = CERTS_DIR / "ca.crt"

            current_checksum = checksum_of_files(ca_crt_path)
            content_checksum = hashlib.sha256(hosts_content.encode()).hexdigest()
            combined = current_checksum + content_checksum

            if combined != last_checksum:
                hosts_toml_path.write_text(hosts_content)
                log.info("Updated %s", hosts_toml_path)
                last_checksum = combined
                log.info("No containerd restart required for hosts.toml updates.")
            else:
                log.debug("No change, sleeping %ds", POLL_INTERVAL_SECONDS)
                time.sleep(POLL_INTERVAL_SECONDS)

        else:
            # --- Legacy inline config.toml path (containerd 1.x without config_path) ---
            working = CONFIG_TOML_BAK.read_text()
            ca_crt_path = CERTS_DIR / "ca.crt"

            current_checksum = checksum_of_files(ca_crt_path, CONFIG_TOML_BAK)

            if current_checksum != last_checksum:
                CONFIG_TOML.write_text(working)
                log.info("Updated %s", CONFIG_TOML)
                last_checksum = current_checksum
                restart_containerd()
            else:
                log.debug("No change, sleeping %ds", POLL_INTERVAL_SECONDS)
                time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
