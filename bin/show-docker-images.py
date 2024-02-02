#!/usr/bin/env python3
"""Show a list of docker images that are deployed by the astronomer platform."""

import subprocess
from pathlib import Path
import yaml
import argparse
import sys
import json


def get_containers_from_spec(spec):
    """Return a list of images used in a kubernetes pod spec."""
    return [
        container["image"]
        for container in spec.get("containers", []) + spec.get("initContainers", [])
    ]


def print_results(items):
    """Print an HTTPS url and the docker pull URL for every image in the list."""
    splits = [image_tag.split(":") for image_tag in items]
    max_length = max(len(x[0]) for x in splits)
    for image, tag in splits:
        print(f"https://{image:{max_length}}  {image}:{tag}")


def default_spec_parser(doc, args):
    """Parse and report on Deployments, StatefulSets, and DaemonSets."""

    item_containers = get_containers_from_spec(doc["spec"]["template"]["spec"])

    if args.verbose:
        print(f"Processing {doc['kind']} {doc['metadata']['name']}")

    if args.private_registry and "quay.io" in yaml.dump(item_containers):
        print(
            f'{doc["kind"]} {doc["metadata"]["name"].removeprefix("release-name-")} uses quay.io'
        )
        if args.verbose:
            print(json.dumps(doc["spec"]["template"]["spec"]))

    return item_containers


def job_template_spec_parser(doc, args):
    """Parse and report on CronJobs, which have a different structure than other pod managers."""

    if args.verbose:
        print(f"Processing {doc['kind']} {doc['metadata']['name']}")

    item_containers = get_containers_from_spec(
        doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    )

    if args.private_registry and "quay.io" in yaml.dump(item_containers):
        print(
            f'{doc["kind"]} {doc["metadata"]["name"].removeprefix("release-name-")} uses quay.io'
        )
        if args.verbose:
            print(json.dumps(doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]))

    return item_containers


def get_images_from_houston_configmap(doc):
    """Return a list of images used in the houston configmap."""
    houston_config = yaml.safe_load(doc["data"]["production.yaml"])
    keepers = ("authSideCar", "loggingSidecar")
    items = {k: v for k, v in houston_config["deployments"].items() if k in keepers}
    auth_sidecar_image = (
        f'{items["authSideCar"]["repository"]}:{items["authSideCar"]["tag"]}'
    )
    logging_sidecar_image = f'{items["loggingSidecar"]["image"]}'
    return (auth_sidecar_image, logging_sidecar_image)


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
    args = parser.parse_args()

    GIT_ROOT = next(
        iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]),
        None,
    )

    command = "helm template . --set forceIncompatibleKubernetes=true -f tests/enable_all_features.yaml"

    if args.private_registry:
        command += (
            " --set global.privateRegistry.repository=example.com/the-private-registry"
            " --set global.privateRegistry.enabled=True"
        )

    if args.verbose:
        print(f"Running: {command}", flush=True, file=sys.stderr)
    output = subprocess.check_output(command, shell=True, cwd=GIT_ROOT).decode("utf-8")
    docs = list(yaml.safe_load_all(output))

    containers = set()

    for doc in docs:
        if doc is None:
            continue
        match doc:
            case {"spec": {"template": {"spec": _}}}:
                containers.update(default_spec_parser(doc, args))
            case {"spec": {"jobTemplate": {"spec": {"template": {"spec": _}}}}}:
                containers.update(job_template_spec_parser(doc, args))
            case {"metadata": {"name": "release-name-houston-config"}}:
                if args.with_houston:
                    containers.update(get_images_from_houston_configmap(doc))
            case _:
                pass

    print_results(sorted(containers))


if __name__ == "__main__":
    main()
