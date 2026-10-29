#!/usr/bin/env python3
"""Load named local Docker images into a KIND cluster's node, failing if one is missing.

Usable from a scenario's `pre_helm_scripts` (tests/functional/scenarios/README.md): it runs
after the cluster exists but before `helm install`, which is the only correct window --
images have to be on the node before the kubelet pulls, and `pullPolicy: Never` means it
never will.

Why this is not already covered: bin/setup-kind.py loads images too, but only ones whose
ref appears in `bin/show-docker-images.py` output, i.e. the chart's DEFAULT image values.
An image referenced solely by a values overlay (a locally built overlay tag, say) is
invisible to it, so the node never gets it.

It fails on a missing image rather than skipping, deliberately. The reason to load a local
image at all is usually that it contains something the published tag does not. Skipping
silently would let the kubelet fall back to the published image and every assertion about
the new behaviour would pass against code that does not have it -- a vacuous green run,
which is worse than a red one. Pair this with `pullPolicy: Never` so a failure here cannot
be papered over by a pull.

--pull inverts that for the one case where it is wrong: an image that IS published but sits
in a private repository, so the node cannot pull it but a logged-in operator can. There the
local store is a cache, not the only copy, and failing because it happens to be cold is just
friction. It stays opt-in because for a locally built image a pull is exactly the silent
fallback described above. It does not make a scenario work on a host that is not logged in
to the registry -- the pull fails and the missing-image error below still fires.

--cluster is REQUIRED and has no default, so a bare invocation cannot act on whatever
cluster happens to be lying around. KIND cluster names are the topology name
(unified/control/data) as created by bin/setup-kind.py.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--cluster",
        required=True,
        help="KIND cluster name to load into, e.g. unified. Required on purpose: no default.",
    )
    parser.add_argument(
        "--pull",
        action="store_true",
        help="docker pull any ref that is not already in the local store, instead of failing on it. "
        "Only for images that are published but private; see the note above.",
    )
    parser.add_argument(
        "images",
        nargs="+",
        metavar="IMAGE",
        help="Image refs to load, e.g. quay.io/astronomer/ap-houston-api:2.2.0-sff",
    )
    return parser.parse_args()


def absent(image: str) -> bool:
    """Whether `image` is missing from the local Docker image store."""
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0


def fetch_platform(image: str) -> str:
    """The os/arch Docker actually materialised locally for `image`, e.g. "linux/amd64".

    `docker pull` fetches only the host's variant of a multi-platform image, but `docker save`
    defaults to writing an index that still references every platform in the manifest list. The
    blobs for the others were never fetched, so `kind load docker-image` -- which imports with
    `ctr --all-platforms` -- fails with "content digest <other platform's manifest>: not found".
    Pinning the save to the one platform that is actually present is what avoids that.
    """
    result = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Os}}/{{.Architecture}}"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> None:
    args = parse_args()

    # Check every image up front, so a typo in the third ref is reported before the first
    # (slow, multi-GB) load rather than after it.
    missing = [image for image in args.images if absent(image)]

    # A pull that fails (not logged in, wrong tag, registry down) is not reported here: the
    # recheck below turns it back into the same missing-image error, which says more.
    if missing and args.pull:
        for image in missing:
            print(f"  pulling {image} ...", flush=True)
            subprocess.run(["docker", "pull", image], check=False)
        missing = [image for image in missing if absent(image)]

    if missing:
        hint = (
            "The pull output above says why -- typically not logged in to the registry, a tag that "
            "does not exist, or a registry rate limit."
            if args.pull
            else "Build them before running this scenario, or pass --pull if they are published."
        )
        raise SystemExit(
            "ERROR: these images are not in the local Docker image store:\n"
            + "\n".join(f"  {image}" for image in missing)
            + f"\n\n{hint} With pullPolicy: Never the pods would fail with "
            "ErrImageNeverPull rather than silently using a published tag."
        )

    with tempfile.TemporaryDirectory() as tmp:
        for image in args.images:
            print(f"  loading {image} into kind cluster {args.cluster!r} ...", flush=True)
            archive = Path(tmp) / "image.tar"
            save = subprocess.run(
                ["docker", "save", "--platform", fetch_platform(image), image, "-o", str(archive)],
                capture_output=True,
                text=True,
            )
            if save.returncode != 0:
                raise SystemExit(f"ERROR: docker save {image} failed:\n{save.stderr}")
            result = subprocess.run(
                ["kind", "load", "image-archive", "--name", args.cluster, str(archive)],
                capture_output=True,
                text=True,
            )
            archive.unlink(missing_ok=True)
            if result.returncode != 0:
                raise SystemExit(f"ERROR: kind load image-archive {image} failed:\n{result.stderr}")

    print(f"{len(args.images)} image(s) loaded into kind cluster {args.cluster!r}.")


if __name__ == "__main__":
    sys.exit(main())
