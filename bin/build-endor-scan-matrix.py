#!/usr/bin/env python3
"""Emit the Endor Labs scan-target matrix for .github/workflows/scan-endorlabs.yaml.

Source of truth: `bin/show-docker-images.py --with-houston`, which renders this chart's
HELM_RUNS + the houston configmap and reports every image:tag pair actually used. This
script just reshapes that list into a GitHub Actions matrix.

Only quay.io/astronomer/* images are kept. That excludes the one non-quay entry
show-docker-images.py currently reports (a core.harbor.astro-qa.link/astrocloud/ap-laminar
value that comes from a test fixture in tests/enable_all_features.yaml, not a real shipped
default) and is a general guard against scanning private-registry test values that `docker
pull` can't reach anonymously in CI.

If $IMAGE_OVERRIDE is set, the matrix collapses to a single entry pointing at that
fully-qualified image reference, bypassing the catalog entirely.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

KEPT_PREFIX = "quay.io/astronomer/"

REPO_ROOT = next(
    iter([x for x in Path(__file__).resolve().parents if (x / ".git").exists()]),
    None,
)


def catalog_targets() -> list[dict[str, str]]:
    script = Path(__file__).resolve().parent / "show-docker-images.py"
    output = subprocess.check_output([sys.executable, str(script), "--with-houston"], cwd=REPO_ROOT, text=True)

    targets = []
    for line in output.splitlines():
        if not line.strip():
            continue
        ref = line.split()[-1]  # last whitespace-separated field is "image:tag"
        if not ref.startswith(KEPT_PREFIX):
            continue
        repo = ref.rpartition(":")[0]
        name = repo.rsplit("/", 1)[-1]
        targets.append({"ref": ref, "name": name})

    if not targets:
        sys.exit(f"No {KEPT_PREFIX}* images found in show-docker-images.py output.")

    return sorted(targets, key=lambda t: t["name"])


def override_target(image_ref: str) -> list[dict[str, str]]:
    if "/" not in image_ref or ":" not in image_ref:
        sys.exit(f"IMAGE_OVERRIDE must be a fully-qualified `registry/repo:tag` reference, got: {image_ref!r}")
    repo, _, _tag = image_ref.rpartition(":")
    name = repo.rsplit("/", 1)[-1]
    return [{"ref": image_ref, "name": name}]


def main() -> None:
    override = os.environ.get("IMAGE_OVERRIDE", "").strip()
    targets = override_target(override) if override else catalog_targets()
    print(json.dumps({"include": targets}, separators=(",", ":")))


if __name__ == "__main__":
    main()
