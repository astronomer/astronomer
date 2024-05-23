#!/usr/bin/env python3

import argparse
import requests
import yaml


def get_latest_versions(repository, num_versions):
    url = f"https://hub.docker.com/v2/repositories/{repository}/tags/"
    response = requests.get(url)
    data = response.json()

    versions = {}
    for tag in data["results"]:
        version = tag["name"]
        # Split version string into major, minor, and patch
        major, minor, patch = [int(x.removeprefix("v")) for x in version.split(".")]
        key = f"{major}.{minor}"
        # Only keep the highest patch version for each major.minor
        if key not in versions or versions[key] < patch:
            versions[key] = patch
    latest_versions = sorted([f"v{key}.{value}" for key, value in versions.items()])

    return [x.removeprefix("v") for x in latest_versions[-num_versions:]]


def generate_yaml(versions):
    return yaml.dump(versions, default_flow_style=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a YAML list of latest Docker image versions"
    )
    parser.add_argument("-n", type=int, default=5, help="Number of versions to include")
    parser.add_argument(
        "--repo",
        type=str,
        default="kindest/node",
        help="Docker repository (e.g., kindest/node)",
    )
    args = parser.parse_args()

    latest_versions = get_latest_versions(args.repo, args.n)
    yaml_list = generate_yaml(latest_versions)
    print(yaml_list.strip())
