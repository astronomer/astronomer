#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#     # Transitive: imports show_docker_images, which parses chart YAML with pyyaml.
#     "pyyaml>=6.0",
# ]
# ///
"""Fail if any platform image is pinned to a release-candidate tag. 🚦

A public release must ship only final image tags. A release-candidate tag (anything whose
version contains an `-rc` segment, e.g. `1.7.0-rc1` or `1.0.0-rc.4`) is an unfinished build and
must never reach a prod release. This gate runs before `release-to-public` in CI and exits
non-zero — blocking the release — when it finds one.

The image list comes from `show_docker_images.py`'s `collect_image_tags(--with-houston)`, the
same resolver the BOM and image-mirroring tooling use, so this checks exactly the images a
release would publish, including the houston-configmap images. That resolver renders the charts
with `helm template` locally; it needs no cluster.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

_BIN = Path(__file__).resolve().parent
if str(_BIN) not in sys.path:
    sys.path.insert(0, str(_BIN))

from show_docker_images import collect_image_tags  # noqa: E402

RC_TAG_PATTERN = re.compile(r"-rc(?:[.-]?\d+)?(?=$|[.\-+])", re.IGNORECASE)


def _image_tags() -> list[str]:
    """Return every `repository:tag` string the platform would publish, incl. houston images."""
    # The same flags a `show_docker_images.py --with-houston` CLI run would set.
    args = SimpleNamespace(with_houston=True, private_registry=False, verbose=False, check_tags=False)
    return sorted(collect_image_tags(args))


def _rc_images(image_tags: list[str]) -> list[str]:
    """Subset of `repository:tag` strings whose tag is a release candidate."""
    rc: list[str] = []
    for ref in image_tags:
        # Split on the LAST colon so a registry port (host:5000/img:tag) doesn't confuse the tag.
        _, _, tag = ref.rpartition(":")
        if RC_TAG_PATTERN.search(tag):
            rc.append(ref)
    return rc


def main() -> int:
    image_tags = _image_tags()
    if not image_tags:
        print("❌ ERROR: image resolver returned no images; refusing to pass the RC check.", file=sys.stderr)
        return 1

    rc = _rc_images(image_tags)
    if rc:
        print("❌ release-candidate image tags found - cannot release to public:", file=sys.stderr)
        for ref in rc:
            print(f"  🔴 {ref}", file=sys.stderr)
        print(
            f"\nFound {len(rc)} RC image(s) out of {len(image_tags)}. Pin each to a final tag before releasing.",
            file=sys.stderr,
        )
        return 1

    print(f"✅ no release-candidate tags among {len(image_tags)} platform images.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
