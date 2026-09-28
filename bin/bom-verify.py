#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "diskcache",
#   "pyyaml",
#   "requests",
#   "rich",
#   "typer",
# ]
# ///
# License: MIT
# Author: github.com/danielhoherd, Claude Sonnet 5
"""Report the version, sha256, architectures, and cosign-signed status of every image in an Astronomer BOM JSON."""

import hashlib
import json
import shutil
import signal
import subprocess
import sys
from enum import StrEnum
from pathlib import Path

import requests
import typer
import yaml
from diskcache import Cache
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False)

BOM_URL_TEMPLATE = "https://updates.astronomer.io/astronomer-software/releases/astronomer-{version}.json"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "bom-verify"
CACHE_EXPIRE_SECONDS = 24 * 60 * 60


def handle_sigint(signum: int, frame: object) -> None:
    """Exit cleanly (no traceback) on Ctrl-C, with the conventional 128+SIGINT exit code.

    Lets a wrapping shell loop that checks the exit status (e.g. `for v in ...; do bom-verify.py "$v" || break; done`)
    correctly detect the interruption and stop, instead of an uncaught KeyboardInterrupt's traceback and exit code 1.
    """
    print("\nInterrupted.", file=sys.stderr)
    sys.exit(128 + signum)


signal.signal(signal.SIGINT, handle_sigint)


class OutputFormat(StrEnum):
    table = "table"
    json = "json"
    yaml = "yaml"


def load_bom(bom: str) -> dict:
    """Load a BOM JSON from a local file path, or fetch it by chart version from updates.astronomer.io."""
    path = Path(bom)
    if path.is_file():
        return json.loads(path.read_text())

    url = BOM_URL_TEMPLATE.format(version=bom)
    response = requests.get(url, timeout=30)
    if not response.ok:
        typer.echo(f"Error: couldn't load a BOM from '{bom}' as a file, or from {url} ({response.status_code})", err=True)
        raise typer.Exit(1)
    return response.json()


def collect_images(data: dict) -> list[dict]:
    """Flatten the astronomer + airflow image sections into one list, tagged by which chart each came from."""
    images = []
    for chart in ("astronomer", "airflow"):
        for name, image in data.get(chart, {}).get("images", {}).items():
            images.append({"chart": chart, "name": name, **image})
    return images


def get_architectures(repository: str, sha256: str) -> list[str]:
    """Return the architectures this image digest was built for."""
    ref = f"{repository}@sha256:{sha256}"
    docker = shutil.which("docker")
    if not docker:
        return ["docker not installed"]
    try:
        result = subprocess.run(
            [docker, "manifest", "inspect", "-v", ref],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        detail = e.stderr.strip().splitlines()[-1] if e.stderr else "inspect failed"
        return [f"error: {detail}"]

    parsed = json.loads(result.stdout)
    entries = parsed if isinstance(parsed, list) else [parsed]
    platforms = set()
    for entry in entries:
        platform = entry.get("Descriptor", {}).get("platform", {})
        arch = platform.get("architecture")
        if not arch or arch == "unknown":
            continue
        variant = platform.get("variant")
        platforms.add(f"{arch}/{variant}" if variant else arch)
    return sorted(platforms) or ["unknown"]


def check_signed(repository: str, sha256: str, public_key: str | None) -> str:
    """Return 'yes', 'yes (unverified)', 'no', or an error string describing the image's cosign-signed status.

    With --public-key, this cryptographically verifies the signature. Without it, this only checks whether a
    signature artifact exists in the registry (via `cosign triangulate` + a manifest lookup), which confirms
    something signed it but not that it was signed with any particular key.
    """
    ref = f"{repository}@sha256:{sha256}"

    cosign = shutil.which("cosign")
    if not cosign:
        return "cosign not installed"

    if public_key:
        result = subprocess.run(
            [cosign, "verify", "--key", public_key, "--insecure-ignore-tlog", ref],
            capture_output=True,
            text=True,
            check=False,
        )
        return "yes" if result.returncode == 0 else "no"

    triangulate = subprocess.run([cosign, "triangulate", ref], capture_output=True, text=True, check=False)
    if triangulate.returncode != 0:
        detail = triangulate.stderr.strip().splitlines()[-1] if triangulate.stderr else "triangulate failed"
        return f"error: {detail}"

    docker = shutil.which("docker")
    if not docker:
        return "docker not installed"
    sig_ref = triangulate.stdout.strip()
    inspect = subprocess.run([docker, "manifest", "inspect", sig_ref], capture_output=True, text=True, check=False)
    return "yes (unverified)" if inspect.returncode == 0 else "no"


def cache_key_for_public_key(public_key: str | None) -> str | None:
    """Return a hash of the public key file's contents, or None.

    check_signed's own `public_key` argument is a file path, and diskcache's memoize keys on argument
    values -- so caching check_signed directly would key on that path string, not the file's actual
    contents. If the file at that path is ever edited in place (a corrected key saved over an old one),
    a memoized run would keep returning the stale result for the old content. Passing this hash as an
    extra argument to the cached wrapper makes the cache key track the key's real contents instead.
    """
    if not public_key:
        return None
    return hashlib.sha256(Path(public_key).read_bytes()).hexdigest()


@app.command()
def main(
    bom: str = typer.Argument(
        ..., help="Path to a BOM JSON file, or a chart version (e.g. 2.1.1) to fetch from updates.astronomer.io."
    ),
    output: OutputFormat = typer.Option(OutputFormat.table, "-o", "--output", help="Output format."),
    public_key: str = typer.Option(
        None,
        "--public-key",
        "-k",
        help="Path to the cosign public key to verify against. Without this, signed status only reports whether "
        "a signature artifact exists, not whether it's cryptographically valid.",
    ),
    include_airflow: bool = typer.Option(True, help="Also check images listed under the airflow chart's own BOM section."),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir", help="Directory for the on-disk registry-lookup cache."),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Bypass the on-disk cache and query the registry fresh for every image."
    ),
):
    data = load_bom(bom)
    images = collect_images(data)
    if not include_airflow:
        images = [image for image in images if image["chart"] != "airflow"]

    def check_signed_keyed(repository: str, sha256: str, public_key: str | None, _public_key_fingerprint: str | None) -> str:
        """check_signed, plus an argument that exists only so the cache keys on the key's contents, not its path."""
        return check_signed(repository, sha256, public_key)

    get_architectures_cached = get_architectures
    check_signed_cached = check_signed_keyed
    if not no_cache:
        cache = Cache(str(cache_dir))
        get_architectures_cached = cache.memoize(expire=CACHE_EXPIRE_SECONDS, tag="architectures")(get_architectures)
        check_signed_cached = cache.memoize(expire=CACHE_EXPIRE_SECONDS, tag="signed")(check_signed_keyed)

    public_key_fingerprint = cache_key_for_public_key(public_key)
    rows = []
    for image in images:
        signed = check_signed_cached(image["repository"], image["sha256"], public_key, public_key_fingerprint)
        rows.append(
            {
                "chart": image["chart"],
                "image": image["repository"],
                "version": image["tag"],
                "sha256": image["sha256"],
                "architectures": get_architectures_cached(image["repository"], image["sha256"]),
                "signed": signed,
            }
        )

    if output is OutputFormat.json:
        typer.echo(json.dumps(rows, indent=2))
        return
    if output is OutputFormat.yaml:
        typer.echo(yaml.dump(rows, sort_keys=False))
        return

    table = Table(title=f"BOM image signing status: {bom}")
    for header in ("Chart", "Image", "Version", "SHA256", "Architectures", "Signed"):
        table.add_column(header)

    signed_count = 0
    for row in rows:
        if row["signed"].startswith("yes"):
            signed_count += 1
        style = "green" if row["signed"].startswith("yes") else ("red" if row["signed"] == "no" else "yellow")
        table.add_row(
            row["chart"],
            row["image"],
            row["version"],
            row["sha256"],
            ", ".join(row["architectures"]),
            row["signed"],
            style=style,
        )

    console = Console()
    console.print(table)
    console.print(f"\n{signed_count}/{len(rows)} images signed")


if __name__ == "__main__":
    app()
