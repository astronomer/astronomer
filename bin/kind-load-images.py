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

--cluster is REQUIRED and has no default, so a bare invocation cannot act on whatever
cluster happens to be lying around. KIND cluster names are the topology name
(unified/control/data) as created by bin/setup-kind.py.
"""

import argparse
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--cluster",
        required=True,
        help="KIND cluster name to load into, e.g. unified. Required on purpose: no default.",
    )
    parser.add_argument(
        "images",
        nargs="+",
        metavar="IMAGE",
        help="Image refs to load, e.g. quay.io/astronomer/ap-houston-api:2.2.0-sff",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Check every image up front, so a typo in the third ref is reported before the first
    # (slow, multi-GB) load rather than after it.
    missing = [
        image for image in args.images if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0
    ]
    if missing:
        raise SystemExit(
            "ERROR: these images are not in the local Docker image store:\n"
            + "\n".join(f"  {image}" for image in missing)
            + "\n\nBuild them before running this scenario. They are not published, so "
            "there is nothing to pull -- and with pullPolicy: Never the pods would fail "
            "with ErrImageNeverPull rather than silently using a published tag."
        )

    for image in args.images:
        print(f"  loading {image} into kind cluster {args.cluster!r} ...", flush=True)
        result = subprocess.run(
            ["kind", "load", "docker-image", "--name", args.cluster, image],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit(f"ERROR: kind load docker-image {image} failed:\n{result.stderr}")

    print(f"{len(args.images)} image(s) loaded into kind cluster {args.cluster!r}.")


if __name__ == "__main__":
    sys.exit(main())
