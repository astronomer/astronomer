#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "requests",
#   "rich",
#   "typer",
# ]
# ///
# License: MIT
# Author: github.com/danielhoherd, Claude Sonnet 5
"""Report the version, sha256, architectures, and cosign-signed status of every image in an Astronomer BOM JSON."""

import json
import shutil
import subprocess
from pathlib import Path

import requests
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False)

BOM_URL_TEMPLATE = "https://updates.astronomer.io/astronomer-software/releases/astronomer-{version}.json"


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


def get_architectures(repository: str, sha256: str) -> str:
    """Return a comma-separated list of architectures this image digest was built for."""
    ref = f"{repository}@sha256:{sha256}"
    docker = shutil.which("docker")
    if not docker:
        return "docker not installed"
    try:
        result = subprocess.run(
            [docker, "manifest", "inspect", "-v", ref],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        detail = e.stderr.strip().splitlines()[-1] if e.stderr else "inspect failed"
        return f"error: {detail}"

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
    return ", ".join(sorted(platforms)) or "unknown"


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


@app.command()
def main(
    bom: str = typer.Argument(
        ..., help="Path to a BOM JSON file, or a chart version (e.g. 2.1.1) to fetch from updates.astronomer.io."
    ),
    public_key: str = typer.Option(
        None,
        "--public-key",
        "-k",
        help="Path to the cosign public key to verify against. Without this, signed status only reports whether "
        "a signature artifact exists, not whether it's cryptographically valid.",
    ),
    include_airflow: bool = typer.Option(True, help="Also check images listed under the airflow chart's own BOM section."),
):
    data = load_bom(bom)
    images = collect_images(data)
    if not include_airflow:
        images = [image for image in images if image["chart"] != "airflow"]

    table = Table(title=f"BOM image signing status: {bom}")
    for header in ("Chart", "Image", "Version", "SHA256", "Architectures", "Signed"):
        table.add_column(header)

    signed_count = 0
    console = Console()
    for image in images:
        signed = check_signed(image["repository"], image["sha256"], public_key)
        if signed.startswith("yes"):
            signed_count += 1
        architectures = get_architectures(image["repository"], image["sha256"])
        style = "green" if signed.startswith("yes") else ("red" if signed == "no" else "yellow")
        table.add_row(
            image["chart"],
            image["repository"],
            image["tag"],
            image["sha256"],
            architectures,
            signed,
            style=style,
        )

    console.print(table)
    console.print(f"\n{signed_count}/{len(images)} images signed")


if __name__ == "__main__":
    app()
