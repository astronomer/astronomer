#!/usr/bin/env python3
"""Update containerd configuration to trust private CA certificates.

This script is deployed as a DaemonSet on every node and continuously monitors
for CA certificate changes, updating the containerd configuration accordingly.

The containerd major version dictates BOTH the plugin namespace AND the
trust-configuration strategy. They cannot be unified because containerd 1.x
forbids mixing `config_path` (hosts.d) with `mirrors` entries in config.toml —
and GKE 1.32's default config.toml ships a `mirrors."docker.io"` block. Writing
`config_path` there would prevent containerd from starting.

  containerd 1.x (GKE <= 1.32):
    - Plugin namespace:  io.containerd.grpc.v1.cri
    - Strategy:          pasted operator-supplied TOML blob (the value of the
                         Helm value `privateCaCertsAddToHost.containerdConfigToml`)
                         is appended to config.toml. The script does not
                         generate registry-trust TOML itself on 1.x — the
                         operator owns the schema choice (typically
                         `configs.<registry>.tls.ca_file`).
    - Restart:           on every CA change (config.toml mutation requires it).
    - Certs still copied to certs.d/<registry>/ so the operator blob can
      reference them by known paths.

  containerd 2.x (GKE >= 1.33):
    - Plugin namespace:  io.containerd.cri.v1.images
    - Strategy:          inject `config_path` once, then manage hosts.d files
                         (certs.d/<registry>/hosts.toml + per-CA PEMs). 2.x
                         removed the inline-mirrors schema so this conflict
                         doesn't exist. The operator's `containerdConfigToml`
                         is ignored — it is not needed on 2.x.
    - Restart:           ONCE at first setup (the `config_path` injection). All
                         subsequent cert rotations are hosts.toml rewrites and
                         require no restart.

Environment variables (injected by the Helm daemonset):
  REGISTRY_HOST          - Registry hostname (e.g. registry.example.com)
  CONTAINERD_HOST_PATH   - Host path to containerd config dir (default: /etc/containerd)
  CERT_CONFIG_PATH       - Host path to containerd certs.d dir (default: /etc/containerd/certs.d)
  PRIVATE_CA_CERTS_DIR   - Path to mounted CA cert secrets (default: /private-ca-certs)
  CONTAINERD_CONFIG_TOML - Operator-supplied TOML blob for containerd 1.x (unused on 2.x)

Requires: Python >= 3.11 (for stdlib tomllib). The DaemonSet runs this script
with the cert-copier image's Python.
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
CONTAINERD_CONFIG_TOML = os.environ.get("CONTAINERD_CONFIG_TOML", "")

CONFIG_TOML = CONTAINERD_HOST_PATH / "config.toml"
CONFIG_TOML_BAK = CONTAINERD_HOST_PATH / "config.toml.bak"

CERTS_DIR_CONTAINER = CONTAINERD_HOST_PATH / "certs.d" / REGISTRY_HOST
CERTS_DIR_HOST = Path(CERT_CONFIG_PATH) / REGISTRY_HOST

CERTS_DIR = CERTS_DIR_CONTAINER

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


_LEGACY_MIRRORS_HEADER_RE = re.compile(
    r'^\[plugins\."io\.containerd\.(grpc\.v1\.cri|cri\.v1\.images)"\.registry\.mirrors\.[^\]]+\]\s*$'
)


def _strip_registry_mirrors_blocks(text: str) -> str:
    """Remove every `[plugins."...".registry.mirrors.<host>]` section (+ its body)
    from config.toml source text.

    Why: `mirrors` and `config_path` are mutually exclusive under a containerd
    registry namespace. On containerd 1.x this combination prevents the daemon
    from starting ("mirrors cannot be set when config_path is provided"). On
    containerd 2.x, the daemon silently blanks `config_path` instead, producing
    a subtler failure — hosts.toml is written but never read by containerd, so
    private-CA trust silently doesn't work.
    """
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    in_mirrors_block = False
    for line in lines:
        stripped = line.lstrip()
        if _LEGACY_MIRRORS_HEADER_RE.match(stripped):
            in_mirrors_block = True
            continue
        if in_mirrors_block:
            # A new top-level section header ends the mirrors block.
            if stripped.startswith("["):
                in_mirrors_block = False
                output.append(line)
            # Otherwise: skip the body line (indented entries like `endpoint = ...`).
            continue
        output.append(line)
    return "".join(output)


def _config_has_legacy_mirrors(config: dict) -> bool:
    """Report whether config.toml has a `registry.mirrors.*` block under either
    the 1.x or the 2.x CRI plugin namespace.

    Both matter because containerd 2.x transposes 1.x-namespace mirrors into the
    2.x namespace at startup; the conflict with `config_path` happens post-
    transpose, so either source is a problem.
    """
    for version in (1, 2):
        subtree = _registry_subtree(config, version)
        if subtree is not None and "mirrors" in subtree:
            return True
    return False


def inject_config_path(containerd_version: int) -> None:
    """Add config_path under the correct plugin namespace and restart containerd once.

    Primarily the containerd 2.x strategy. See module docstring for why 1.x uses
    a different path.
    """
    plugin = PLUGIN_NS[containerd_version]
    keypath = plugin["keypath"]
    parsed = _parse_config_toml(CONFIG_TOML)
    subtree = _registry_subtree(parsed, containerd_version)

    has_config_path = subtree is not None and "config_path" in subtree
    has_mirrors = _config_has_legacy_mirrors(parsed)

    if has_config_path and not has_mirrors:
        log.info(
            "config_path already set under [%s] and no legacy mirrors to strip; "
            "nothing to do.",
            plugin["header"],
        )
        return

    source_text = CONFIG_TOML.read_text()
    stripped_text = _strip_registry_mirrors_blocks(source_text)
    if stripped_text != source_text:
        log.info(
            "Stripped legacy `registry.mirrors.*` block(s) from config.toml "
            "(incompatible with config_path under containerd 2.x)."
        )

    # Only append config_path if it isn't already there — avoids producing
    # duplicate `config_path` keys under the same table.
    if has_config_path:
        candidate = stripped_text
    else:
        stanza = f'\n[{plugin["header"]}]\n  config_path = "{CERT_CONFIG_PATH}"\n'
        candidate = stripped_text + stanza

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
    log.info("Reconciled config.toml: config_path=%s, mirrors removed.", CERT_CONFIG_PATH)
    restart_containerd()


def write_customer_config_toml(blob: str) -> bool:
    """Append an operator-supplied TOML blob to config.toml, containerd 1.x style.

    This is the containerd 1.x strategy. We do NOT generate registry-trust TOML
    ourselves here; the operator supplies the fragment via the Helm value
    `privateCaCertsAddToHost.containerdConfigToml`, and we paste it verbatim
    into config.toml.

    The typical blob looks like:

        [plugins."io.containerd.grpc.v1.cri".registry.configs."<registry>".tls]
          ca_file = "/etc/containerd/certs.d/<registry>/<ca>.pem"

    Raises:
        RuntimeError: blob is empty (nothing to apply) or produces invalid TOML.
    """
    if not blob.strip():
        log.error(
            "CONTAINERD_CONFIG_TOML is empty. On containerd 1.x, the operator "
            "must set `global.privateCaCertsAddToHost.containerdConfigToml` to "
            "a TOML fragment that tells containerd to trust the mounted CA. "
            "Upgrade to GKE 1.33+ (containerd 2.x) to let the script manage "
            "this automatically.",
        )
        raise RuntimeError("containerdConfigToml is required on containerd 1.x")

    # Ensure the appended blob starts on a fresh line so it can't accidentally
    # merge into a pre-existing key on the last line of config.toml.
    candidate = CONFIG_TOML_BAK.read_text().rstrip() + "\n\n" + blob.rstrip() + "\n"

    try:
        tomllib.loads(candidate)
    except tomllib.TOMLDecodeError as exc:
        log.error(
            "Refusing to write: containerdConfigToml produces invalid TOML: %s. "
            "Check the value of global.privateCaCertsAddToHost.containerdConfigToml.",
            exc,
        )
        raise RuntimeError("containerdConfigToml produces invalid TOML") from exc

    # Skip the write + restart if the file already matches — keeps steady-state
    # ticks cheap.
    if CONFIG_TOML.is_file() and CONFIG_TOML.read_text() == candidate:
        return False

    CONFIG_TOML.write_text(candidate)
    log.info("Applied operator-supplied containerdConfigToml (%d bytes)", len(blob))
    return True


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

    Returns the sorted list of **host-side** PEM paths (CERTS_DIR_HOST / name).
    Callers embed these straight into config.toml / hosts.toml, both of which
    are read by containerd running on the host — so the paths must be what the
    host sees, not the container mount. For filesystem I/O (checksumming the
    written files), callers can convert via `_host_to_container_path()`.
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

    CERTS_DIR_CONTAINER.mkdir(parents=True, exist_ok=True)
    host_paths: list[Path] = []
    for pem_file in sources:
        dest_container = CERTS_DIR_CONTAINER / pem_file.name
        dest_host = CERTS_DIR_HOST / pem_file.name
        shutil.copy2(pem_file, dest_container)
        host_paths.append(dest_host)
        log.info("Copied %s -> %s (host path: %s)", pem_file, dest_container, dest_host)
    return host_paths


def _host_to_container_path(host_path: Path) -> Path:
    """Translate a host-absolute path under CERT_CONFIG_PATH to the container's
    view through the CONTAINERD_HOST_PATH hostPath mount.

    Used for filesystem I/O (checksumming) on paths returned by copy_ca_certs().
    """
    return CERTS_DIR_CONTAINER / host_path.name


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
def _startup(containerd_version: int) -> None:
    """
    One-time setup that must complete before we enter the poll loop.
    """
    if containerd_version != 2:
        return
    try:
        inject_config_path(containerd_version)
    except RuntimeError:
        sys.exit(1)


def _apply_v2_hosts_toml(ca_files: list[Path], last_output_checksum: str) -> str:
    """Write certs.d/<registry>/hosts.toml for the 2.x strategy. Returns the
    checksum of what's now on disk so the loop can short-circuit next tick.

    `ca_files` are host-side paths (what we wrote into hosts.toml). For the
    on-disk checksum we translate to the container view because file I/O only
    works through the hostPath mount, not through the host-absolute path.
    """
    hosts_content = generate_hosts_toml(ca_files)
    hosts_toml_path = CERTS_DIR_CONTAINER / "hosts.toml"

    container_paths = [_host_to_container_path(p) for p in ca_files]
    current_checksum = checksum_of_files(*container_paths)
    content_checksum = hashlib.sha256(hosts_content.encode()).hexdigest()
    combined = current_checksum + content_checksum

    if combined != last_output_checksum:
        hosts_toml_path.write_text(hosts_content)
        log.info("Updated %s", hosts_toml_path)
        return combined
    log.debug("No change in hosts.toml or CA certs")
    return last_output_checksum


def _apply_v1_customer_toml() -> None:
    """Append the operator-supplied TOML blob to config.toml for 1.x; restart if changed.

    The CA PEMs are copied to certs.d/ by the caller (so the operator's blob
    can reference them by path), but we don't inspect or transform them here —
    the blob owns the registry trust schema on 1.x.
    """
    try:
        changed = write_customer_config_toml(CONTAINERD_CONFIG_TOML)
    except RuntimeError:
        sys.exit(1)
    if changed:
        restart_containerd()


def _poll_loop(containerd_version: int) -> None:
    """Main reconcile loop — polls mounted PEMs, applies the version-specific
    strategy, and sleeps. Short-circuits on unchanged sources."""
    last_source_checksum = ""
    last_output_checksum = ""

    while True:
        current_source = source_pem_checksum()
        if current_source == last_source_checksum:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        last_source_checksum = current_source

        ca_files = copy_ca_certs()

        if containerd_version == 2:
            last_output_checksum = _apply_v2_hosts_toml(ca_files, last_output_checksum)
        else:
            _apply_v1_customer_toml()

        time.sleep(POLL_INTERVAL_SECONDS)


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

    strategy = (
        "operator-supplied containerdConfigToml" if containerd_version == 1
        else "hosts.d (config_path + hosts.toml)"
    )
    log.info("Detected containerd %d.x; using %s strategy", containerd_version, strategy)

    _startup(containerd_version)
    _poll_loop(containerd_version)


if __name__ == "__main__":
    main()