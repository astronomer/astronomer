#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""Show a list of docker images that are deployed by the astronomer platform."""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import yaml

GIT_ROOT = next(
    iter([x for x in Path(__file__).resolve().parents if (x / ".git").exists()]),
    None,
)

# The C loader is several times faster on the ~100k lines helm renders, when pyyaml has it.
YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

PRIVATE_REGISTRY = "example.com/the-private-registry"
HOUSTON_CONFIGMAP = "release-name-houston-config"

# Helm is run once for each of these list items, and images from all runs are aggregated into
# one list. This allows us to discover more images that would not be discovered due to mutually
# incompatible configurations, like plane.mode.
HELM_RUNS = [
    {"label": "unified", "files": ["tests/enable_all_features.yaml"]},
    {"label": "control", "files": ["configs/enable-all-features-control.yaml"]},
    {"label": "data", "files": ["configs/enable-all-features-data.yaml"]},
    {"label": "extras", "files": ["configs/enable-all-features-extras.yaml"]},
]

# An image ref with a registry host, like quay.io/astronomer/ap-base:1.2.3. This is matched against
# every string in the rendered output, so it has to be strict enough not to match URLs.
REGISTRY_IMAGE_REF = re.compile(r"(?:[a-z0-9-]+\.)+[a-z0-9-]+(?::\d+)?(?:/[a-z0-9._-]+)+:\w[\w.-]{0,127}")
# Any image ref, like busybox:1.36. Only matched under keys that name an image.
ANY_IMAGE_REF = re.compile(r"[a-z0-9._/-]+:\w[\w.-]{0,127}")
# A registry image ref inside free text, like the Python in Houston's airflowLocalSettings.
TEXT_IMAGE_REF = re.compile(rf"(?<![\w./:-]){REGISTRY_IMAGE_REF.pattern}(?![\w/:-])")


def find_images(node, path=()):
    """Yield (image, path) for every image ref in a parsed YAML tree.

    An image is a string that looks like an image ref, or a dict with `repository` and `tag` (and
    an optional `registry`). Strings that hold a whole YAML or JSON document, like ConfigMap data,
    are parsed and searched too; other multi-line text is searched for registry image refs.
    """
    if isinstance(node, dict):
        repository, tag, registry = node.get("repository"), node.get("tag"), node.get("registry")
        has_tag = isinstance(tag, (str, int, float)) and not isinstance(tag, bool) and str(tag)
        if isinstance(repository, str) and repository and has_tag:
            image = f"{repository}:{tag}"
            yield (f"{registry}/{image}" if isinstance(registry, str) and registry else image), path
        for key, value in node.items():
            yield from find_images(value, (*path, str(key)))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from find_images(item, (*path, index))
    elif isinstance(node, str):
        key = next((p for p in reversed(path) if isinstance(p, str)), "")
        if REGISTRY_IMAGE_REF.fullmatch(node) or ("image" in key.lower() and ANY_IMAGE_REF.fullmatch(node)):
            yield node, path
        elif "\n" in node or node.startswith(("{", "[")):
            try:
                embedded = yaml.safe_load(node)
            except yaml.YAMLError:
                embedded = None
            if isinstance(embedded, (dict, list)):
                yield from find_images(embedded, path)
            else:
                for match in TEXT_IMAGE_REF.finditer(node):
                    yield match.group(), path


def print_results(items):
    """Print an HTTPS url and the docker pull URL for every image in the list."""
    splits = [image_tag.rpartition(":")[::2] for image_tag in items]
    max_length = max(len(x[0]) for x in splits)
    for image, tag in splits:
        print(f"https://{image:{max_length}}  {image}:{tag}")


def images_in_doc(doc, args):
    """Return the images in one rendered document, reporting any that skip the private registry."""
    images = {image for image, _ in find_images(doc)}
    if not images:
        return images

    kind, name = doc.get("kind"), doc.get("metadata", {}).get("name", "")
    if args.verbose:
        print(f"Processing {kind} {name}", file=sys.stderr)

    if args.private_registry:
        for image in sorted(images):
            if not image.startswith(f"{PRIVATE_REGISTRY}/"):
                print(f"{kind} {name.removeprefix('release-name-')} uses {image} instead of private registry")

    return images


def deep_merge(base, override):
    """Merge override into base, the way helm merges parent chart values into a subchart's."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def images_in_values():
    """Return {image: where} for every image set in the chart's values files.

    Each subchart's values have the parent chart's overrides for it applied, so a tag bumped in the
    top-level values.yaml is reported at its bumped value.
    """
    with open(GIT_ROOT / "values.yaml") as f:
        root = yaml.safe_load(f)
    subcharts = sorted(p.parent.name for p in (GIT_ROOT / "charts").glob("*/values.yaml"))

    trees = {"values.yaml": {k: v for k, v in root.items() if k not in subcharts}}
    for name in subcharts:
        with open(GIT_ROOT / "charts" / name / "values.yaml") as f:
            trees[f"charts/{name}/values.yaml"] = deep_merge(yaml.safe_load(f) or {}, root.get(name) or {})

    images = {}
    for filename, tree in trees.items():
        for image, path in find_images(tree):
            images.setdefault(image, f"{filename}: {'.'.join(map(str, path))}")
    return images


def helm_template(args, label, files):
    """Run helm template for the given value files and return the parsed yaml."""
    command = "helm template . --set forceIncompatibleKubernetes=true"
    for f in files:
        command += f" -f {f}"
    if args.private_registry:
        command += f" --set global.privateRegistry.repository={PRIVATE_REGISTRY} --set global.privateRegistry.enabled=True"

    if args.verbose:
        print(f"Running helm template [{label}]: {command}", flush=True, file=sys.stderr)
    output = subprocess.check_output(command, shell=True, cwd=GIT_ROOT).decode("utf-8")

    return [doc for doc in yaml.load_all(output, Loader=YAML_LOADER) if doc]


def collect_image_tags(args):
    """
    Render the platform charts and return the set of `repository:tag` strings they deploy.

    Every rendered document is searched, not just pod specs, so images in CRD defaults, env vars
    and config files are found too. Images set in chart values are added as well: some, like the
    Airflow images Houston deploys, never render as a pod. Any that no helm run renders at all are
    reported, since they ship with the chart even though no run turns on what uses them.
    """
    rendered = set()
    houston = set()
    for run in HELM_RUNS:
        for doc in helm_template(args, run["label"], run["files"]):
            if doc.get("kind") == "ConfigMap" and doc.get("metadata", {}).get("name") == HOUSTON_CONFIGMAP:
                houston.update(image for image, _ in find_images(doc))
            else:
                rendered.update(images_in_doc(doc, args))

    if args.verbose and args.private_registry and any(not x.startswith(f"{PRIVATE_REGISTRY}/") for x in houston):
        print("Houston configmap uses images outside the private registry", file=sys.stderr)

    containers = rendered | houston if args.with_houston else rendered

    # Values hold the upstream refs, which can't be compared with private-registry renders.
    if not args.private_registry:
        values = images_in_values()
        containers |= set(values)
        unrendered = {image: where for image, where in values.items() if image not in rendered | houston}
        if unrendered:
            print(
                "WARNING: these images are set in chart values but no helm run renders them. "
                "Turn on what uses them in a HELM_RUNS values file:",
                file=sys.stderr,
            )
            for image, where in sorted(unrendered.items()):
                print(f"  {image}  ({where})", file=sys.stderr)

    return containers


def main():
    """Parse the helm output and print the images."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--private-registry",
        action="store_true",
        help="show images when using private registry",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="be verbose")
    parser.add_argument(
        "--with-houston",
        action="store_true",
        help="include images from houston configmap",
    )
    parser.add_argument(
        "-c",
        "--check-tags",
        action="store_true",
        help="only check for multiple tags for the same image, do not print the images",
    )
    args = parser.parse_args()

    containers = collect_image_tags(args)

    if args.check_tags:
        image_tag_counts = defaultdict(int)
        for x, y in [(tag.rpartition(":")[0], tag.rpartition(":")[2]) for tag in containers]:
            image_tag_counts[x] += 1
        for image, count in image_tag_counts.items():
            if count > 1:
                print(
                    f"ALERT: {image} has {count} different tags: {', '.join([c.rpartition(':')[-1] for c in containers if image in c])}"
                )
        # Exit with a return code equal to the number of images with multiple tags
        raise SystemExit(len([y for x, y in image_tag_counts.items() if y > 1]))

    print_results(sorted(containers))


if __name__ == "__main__":
    main()
