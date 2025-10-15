#!/usr/bin/env python3
# Author: github.com/danielhoherd, GH Copilot GPT-4.1
# License: MIT
# Description: Fetch recent kind node image versions from Docker Hub and print the most recent semver representations.

import requests
import semver


def get_recent_tags(namespace: str, repo: str, page_size: int = 25) -> list[str]:
    """Fetch recent tags from Docker Hub and return the most recent patch version for each minor version."""
    url = f"https://hub.docker.com/v2/repositories/{namespace}/{repo}/tags?page_size={page_size}&ordering=last_updated"
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    data = response.json()
    return [result["name"] for result in data["results"] if semver.VersionInfo.parse(result["name"].lstrip("v"))]


def filter_tag_list(versions: list[str]) -> list[str]:
    """Filter the list of versions to include only the most recent patch version for each minor version."""
    seen = {}
    for version in versions:
        parsed = semver.VersionInfo.parse(version.lstrip("v"))
        major_minor = f"{parsed.major}.{parsed.minor}"
        if not seen.get(major_minor):
            seen[major_minor] = version
    return list(seen.values())


if __name__ == "__main__":
    namespace = "kindest"
    repo = "node"
    recent_tags = get_recent_tags(namespace, repo, page_size=25)
    recent_tags = [tag.lstrip("v") for tag in filter_tag_list(recent_tags)]
    for tag in sorted(recent_tags, key=semver.VersionInfo.parse):
        print("-", tag)
