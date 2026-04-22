#!/usr/bin/env python3
"""Update containerd configuration to trust private CA certificates.

This script is deployed as a DaemonSet on every node and continuously monitors
for CA certificate changes, updating the containerd configuration accordingly.

Behaviour (same for both containerd 1.x and 2.x — only the plugin namespace
differs, auto-detected via `containerd --version`):

  Plugin namespace:
    - containerd 1.x (GKE <= 1.32): io.containerd.grpc.v1.cri
    - containerd 2.x (GKE >= 1.33): io.containerd.cri.v1.images

  On startup:
    - If `config_path` is already set under the version's plugin namespace,
      nothing changes in config.toml.
    - Otherwise, inject `config_path = "<certs.d>"` under the correct namespace
      and restart containerd ONCE so it picks up the hosts.d layout.

  Steady state (both versions):
    - certs.d/<registry>/<secret>.pem per mounted CA.
    - certs.d/<registry>/hosts.toml referencing every PEM in its `ca = [...]` key.
    - No further containerd restarts on cert rotation.

Environment variables (injected by the Helm daemonset):
  REGISTRY_HOST         - Registry hostname (e.g. registry.example.com)
  CONTAINERD_HOST_PATH  - Host path to containerd config dir (default: /etc/containerd)
  CERT_CONFIG_PATH      - Host path to containerd certs.d dir (default: /etc/containerd/certs.d)
  PRIVATE_CA_CERTS_DIR  - Path to mounted CA cert secrets (default: /private-ca-certs)

Requires: Python >= 3.11 (for stdlib tomllib). The DaemonSet runs this script
with the cert-copier image's Python
"""

import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
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

# Plugin namespaces per containerd major version.
#   header:   the TOML section header we write (quoted form, as it appears in config.toml)
#   keypath:  the sequence of keys we traverse in a parsed TOML dict to reach the
#             registry subtree (tomllib returns dotted-quoted plugin names as
#             nested dicts keyed by each segment, with interior-quoted names
#             collapsed into a single key — see containerd docs for the layout).
PLUGIN_NS = {
    1: {
        "header": 'plugins."io.containerd.grpc.v1.cri".registry',
        "keypath": ("plugins", "io.containerd.grpc.v1.cri", "registry"),
    },
    2: {
        "header": 'plugins."io.containerd.cri.v1.images".registry',
        "keypath": ("plugins", "io.containerd.cri.v1.images", "registry"),
    },
}

POLL_INTERVAL_SECONDS = 1

# Hostname / FQDN for the image registry (e.g. registry.example.com). Conservative ASCII subset.
_REGISTRY_HOST_PATTERN = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def validate_registry_host(host: str) -> None:
    """Ensure REGISTRY_HOST is non-empty and safe for paths and TOML.

    Raises:
        ValueError: If the value is empty, has unsafe characters, or fails validation.
    """
    if not host or not host.strip():
        raise ValueError("REGISTRY_HOST is required and must be non-empty")
    if host != host.strip():
        raise ValueError("REGISTRY_HOST must not have leading or trailing whitespace")
    if any(ch.isspace() for ch in host):
        raise ValueError("REGISTRY_HOST must not contain whitespace")
    if "/" in host or "\\" in host:
        raise ValueError("REGISTRY_HOST must not contain path separators")
    if ".." in host:
        raise ValueError("REGISTRY_HOST must not contain '..'")
    if len(host) > 253:
        raise ValueError("REGISTRY_HOST is too long")
    if not _REGISTRY_HOST_PATTERN.match(host):
        raise ValueError(
            "REGISTRY_HOST must be a valid DNS hostname (ASCII letters, digits, dots, hyphens)",
        )


def ensure_nsenter_available() -> None:
    """Verify nsenter is on PATH before attempting host-namespace operations.

    The DaemonSet relies on nsenter to enter the host's namespaces for
    `containerd --version` and `systemctl restart containerd`. If nsenter is
    missing, every downstream operation will fail with confusing errors — so we
    preflight here and die with an actionable message instead.

    Raises:
        RuntimeError: If nsenter is not available on PATH.
    """
    if shutil.which("nsenter") is None:
        log.error(
            "nsenter is not available on PATH. This script must run in a container "
            "image that provides util-linux (nsenter)"
        )
        raise RuntimeError("nsenter not available; cannot manage containerd on host")


def detect_containerd_version() -> int:
    """Detect the major version of containerd running on the host.

    Uses nsenter to run `containerd --version` in the host PID namespace.
    Returns 1 or 2.

    Raises:
        RuntimeError: If the version cannot be determined (missing binary, non-zero exit,
            or unrecognized output).
    """
    try:
        result = subprocess.run(
            ["nsenter", "--target", "1", "--mount", "--uts", "--ipc", "--net", "--pid", "containerd", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.error("Failed to execute containerd --version on host: %s", exc)
        raise RuntimeError("cannot detect containerd version") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        log.error(
            "containerd --version exited with code %s: %s",
            result.returncode,
            stderr,
        )
        raise RuntimeError("containerd --version failed on host")

    version_output = result.stdout.strip()
    log.info("containerd version output: %s", version_output)

    # Example outputs:
    #   containerd github.com/containerd/containerd 1.7.29 ...
    #   containerd github.com/containerd/containerd/v2 2.0.7 ...
    for token in version_output.split():
        if token and token[0].isdigit():
            try:
                major = int(token.split(".", 1)[0])
            except ValueError:
                continue
            if major in (1, 2):
                log.info("Detected containerd major version: %d", major)
                return major

    log.error("Could not determine containerd major version from: %r", version_output)
    raise RuntimeError("unrecognized containerd --version output")


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


def _parse_config_toml(path: Path) -> dict:
    """Parse a containerd config.toml into a dict using the stdlib TOML reader.

    Raises:
        RuntimeError: If the file cannot be parsed as TOML. We fail loudly rather
            than silently falling back to string handling, because an unparseable
            config.toml means we cannot make structural decisions about it.
    """
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.error("Failed to parse %s: %s", path, exc)
        raise RuntimeError(f"cannot parse {path}") from exc


def _registry_subtree(config: dict, containerd_version: int) -> dict | None:
    """Walk the parsed config dict down to the plugin's registry table.

    Returns the subtree dict, or None if the plugin namespace isn't present.
    """
    node = config
    for key in PLUGIN_NS[containerd_version]["keypath"]:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node if isinstance(node, dict) else None


def config_path_is_set(config_path_file: Path, containerd_version: int) -> bool:
    """Check whether `config_path` is set under the version-appropriate plugin namespace.

    Parses config.toml so:
      * A `config_path` under a different plugin namespace doesn't false-match.
      * A `config_path` in a comment doesn't false-match.
      * Malformed TOML fails loudly instead of producing a silent wrong answer.
    """
    config = _parse_config_toml(config_path_file)
    subtree = _registry_subtree(config, containerd_version)
    return bool(subtree) and "config_path" in subtree


def inject_config_path(containerd_version: int) -> None:
    """Add config_path under the correct plugin namespace and restart containerd once.

    Safety:
      * No-op if `config_path` is already present under the target namespace.
      * After writing, parses the resulting text and confirms that
        `config_path` resolves to the expected value under the expected namespace.
        If the parse fails, or the key doesn't land where we expect, the original
        file is left untouched.

    We append a `[<plugin>.registry]` section header followed by the key. TOML
    allows promoting an implicitly-declared table (e.g. via a pre-existing
    `[...registry.mirrors."docker.io"]` on GKE 1.32) to an explicit one, so this
    form is valid whether or not the namespace was implicitly touched by
    earlier sections.
    """
    plugin = PLUGIN_NS[containerd_version]
    keypath = plugin["keypath"]
    parsed = _parse_config_toml(CONFIG_TOML_BAK)
    subtree = _registry_subtree(parsed, containerd_version)
    if subtree is not None and "config_path" in subtree:
        log.info("config_path already set under [%s]; nothing to inject", plugin["header"])
        return

    stanza = f'\n[{plugin["header"]}]\n  config_path = "{CERT_CONFIG_PATH}"\n'
    candidate = CONFIG_TOML_BAK.read_text() + stanza

    try:
        reparsed = tomllib.loads(candidate)
    except tomllib.TOMLDecodeError as exc:
        log.error("Refusing to write: injected config.toml would be invalid TOML: %s", exc)
        raise RuntimeError("injected config.toml would be invalid TOML") from exc

    node = reparsed
    for key in keypath:
        if not isinstance(node, dict) or key not in node:
            log.error("Post-inject parse did not find %s in expected location", ".".join(keypath))
            raise RuntimeError("post-inject validation: keypath missing")
        node = node[key]
    if not isinstance(node, dict) or node.get("config_path") != CERT_CONFIG_PATH:
        log.error("Post-inject parse did not find config_path=%r under %s", CERT_CONFIG_PATH, keypath)
        raise RuntimeError("post-inject validation: config_path missing or wrong value")

    CONFIG_TOML.write_text(candidate)
    log.info("Injected config_path under [%s]", plugin["header"])
    restart_containerd()


def generate_hosts_toml(ca_files: list[Path]) -> str:
    """Generate a hosts.toml that trusts every CA PEM in `ca_files`.

    containerd's `ca` key accepts a list of paths, so multiple CAs are
    expressed as a TOML array rather than a single path.
    """
    ca_list = ", ".join(f'"{p}"' for p in ca_files)
    return (
        f'server = "https://{REGISTRY_HOST}"\n'
        f"\n"
        f'[host."https://{REGISTRY_HOST}"]\n'
        f'  capabilities = ["pull", "resolve"]\n'
        f"  ca = [{ca_list}]\n"
    )


def copy_ca_certs() -> list[Path]:
    """Copy each mounted CA PEM into certs.d/<registry>/ under its source filename.

    `global.privateCaCerts` is a list, so customers can mount multiple CA
    secrets. Each PEM keeps its own filename on disk so containerd sees one
    file per CA. The hosts.toml written elsewhere in this script lists every
    PEM under its `ca = [...]` key, which is how containerd trusts all of them.

    Returns the sorted list of PEM paths now present on disk. Callers use this
    to build the `ca` list in hosts.toml so the two stay in sync.
    """
    if not PRIVATE_CA_CERTS_DIR.is_dir():
        return []

    sources: list[Path] = []
    for secret_dir in sorted(PRIVATE_CA_CERTS_DIR.iterdir()):
        if not secret_dir.is_dir():
            continue
        sources.extend(sorted(secret_dir.glob("*.pem")))

    if not sources:
        return []

    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for pem_file in sources:
        dest = CERTS_DIR / pem_file.name
        shutil.copy2(pem_file, dest)
        copied.append(dest)
        log.info("Copied %s -> %s", pem_file, dest)
    return copied


def source_pem_checksum() -> str:
    """Checksum every PEM under PRIVATE_CA_CERTS_DIR.

    Used as a cheap "has anything changed upstream?" check so the main loop can
    skip the CA-copy + hosts.toml churn on ticks where secrets haven't rotated.
    """
    if not PRIVATE_CA_CERTS_DIR.is_dir():
        return ""
    pems = sorted(PRIVATE_CA_CERTS_DIR.glob("*/*.pem"))
    return checksum_of_files(*pems)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    try:
        validate_registry_host(REGISTRY_HOST)
    except ValueError as exc:
        log.error("%s", exc)
        sys.exit(1)

    try:
        ensure_nsenter_available()
    except RuntimeError:
        sys.exit(1)

    if not CONFIG_TOML.is_file():
        log.error("No %s found. Is this a containerd node?", CONFIG_TOML)
        sys.exit(1)

    backup_config_toml()

    try:
        containerd_version = detect_containerd_version()
    except RuntimeError:
        sys.exit(1)

    log.info("Using containerd version %d strategy", containerd_version)

    try:
        has_config_path = config_path_is_set(CONFIG_TOML, containerd_version)
    except RuntimeError:
        sys.exit(1)

    # Ensure config_path is set under the version's plugin namespace so
    # certs.d/hosts.toml is honoured. Same approach for 1.x and 2.x — the only
    # thing that differs is the plugin namespace, which `inject_config_path`
    # looks up via PLUGIN_NS.
    if not has_config_path:
        log.info("config_path not found under correct plugin namespace, injecting...")
        try:
            inject_config_path(containerd_version)
        except RuntimeError:
            sys.exit(1)

    log.info("Using certs.d/hosts.toml approach (no restarts on cert rotation)")

    last_source_checksum = ""
    last_output_checksum = ""

    while True:
        # Cheap short-circuit: if the mounted PEMs haven't changed since the last
        # tick, there's nothing to do. Skips the disk churn of re-copying certs
        # and re-writing hosts.toml every poll interval.
        current_source = source_pem_checksum()
        if current_source == last_source_checksum:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        last_source_checksum = current_source

        ca_files = copy_ca_certs()

        hosts_content = generate_hosts_toml(ca_files)
        hosts_toml_path = CERTS_DIR / "hosts.toml"

        current_checksum = checksum_of_files(*ca_files)
        content_checksum = hashlib.sha256(hosts_content.encode()).hexdigest()
        combined = current_checksum + content_checksum

        if combined != last_output_checksum:
            hosts_toml_path.write_text(hosts_content)
            log.info("Updated %s", hosts_toml_path)
            last_output_checksum = combined
        else:
            log.debug("No change in hosts.toml or CA certs")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
