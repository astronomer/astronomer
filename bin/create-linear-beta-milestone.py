#!/usr/bin/env python3
"""
Create a Linear project milestone when a beta/RC Astronomer Helm chart tarball is published.

Reads chart version from an astronomer-*.tgz file in the workspace and calls the Linear GraphQL API.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, UTC
from pathlib import Path

import requests

DEFAULT_GRAPHQL_URL = "https://api.linear.app/graphql"
DEFAULT_PROJECT_NAME = "APC RC tracker"
DEFAULT_MILESTONE_DESCRIPTION = "New Beta/RC chart is released"
REQUEST_TIMEOUT_SEC = 60

_FIND_PROJECT_QUERY = """
query FindProject($name: String!) {
  projects(filter: { name: { eq: $name } }) {
    nodes {
      id
      name
    }
  }
}
"""

_CREATE_MILESTONE_MUTATION = """
mutation CreateMilestone($projectId: String!, $name: String!, $description: String!) {
  projectMilestoneCreate(
    input: { projectId: $projectId, name: $name, description: $description }
  ) {
    success
    projectMilestone {
      id
      name
    }
  }
}
"""


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("/tmp/workspace"),
        help="Directory containing astronomer-*.tgz (default: /tmp/workspace)",
    )
    parser.add_argument(
        "--graphql-url",
        default=os.environ.get("LINEAR_GRAPHQL_URL", DEFAULT_GRAPHQL_URL),
        help="Linear GraphQL endpoint",
    )
    parser.add_argument(
        "--project-name",
        default=os.environ.get("LINEAR_PROJECT_NAME", DEFAULT_PROJECT_NAME),
        help="Linear project name to attach the milestone to",
    )
    parser.add_argument(
        "--milestone-description",
        default=os.environ.get("LINEAR_MILESTONE_DESCRIPTION", DEFAULT_MILESTONE_DESCRIPTION),
        help="Description stored on the new milestone",
    )
    return parser.parse_args()


def extract_chart_version(archive_path: Path) -> str:
    """
    Extract the chart version string from an astronomer-<version>.tgz filename.

    Parameters:
        archive_path: Path whose name matches astronomer-<version>.tgz.

    Returns:
        The chart version segment between 'astronomer-' and '.tgz'.
    """
    match = re.fullmatch(r"astronomer-(.+)\.tgz", archive_path.name)
    if not match:
        raise ValueError(f"Expected filename matching astronomer-<version>.tgz; got {archive_path.name!r}")
    return match.group(1)


def find_chart_archive(workspace: Path) -> Path:
    """
    Locate exactly one astronomer chart tarball under the workspace root.

    Parameters:
        workspace: Root directory to search (non-recursive).

    Returns:
        Path to the chart archive.

    Raises:
        FileNotFoundError: If the workspace or no matching archive exists.
        RuntimeError: If more than one matching archive exists.
    """
    if not workspace.is_dir():
        raise FileNotFoundError(f"Workspace directory does not exist: {workspace}")

    matches = sorted(workspace.glob("astronomer-*.tgz"))
    if not matches:
        raise FileNotFoundError(f"No astronomer-*.tgz found under {workspace}")
    if len(matches) == 1:
        return matches[0]
    names = ", ".join(p.name for p in matches)
    raise RuntimeError(f"Expected exactly one astronomer-*.tgz in {workspace}; found {len(matches)}: {names}")


def linear_graphql(url: str, api_key: str, payload: dict) -> dict:
    """
    POST a GraphQL request to Linear and return the parsed JSON body.

    Parameters:
        url: Linear GraphQL endpoint.
        api_key: Linear API key (sent as Authorization header).
        payload: JSON-serializable GraphQL request body.

    Returns:
        Parsed response JSON.

    Raises:
        requests.HTTPError: On non-success HTTP status.
        RuntimeError: When the response contains GraphQL errors.
    """
    response = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json", "Authorization": api_key},
        timeout=REQUEST_TIMEOUT_SEC,
    )
    response.raise_for_status()
    body: dict = response.json()
    errors = body.get("errors")
    if errors:
        raise RuntimeError(f"Linear GraphQL errors: {json.dumps(errors)}")
    return body


def find_project_id(url: str, api_key: str, project_name: str) -> str:
    """
    Resolve a Linear project id by exact project name.

    Parameters:
        url: Linear GraphQL endpoint.
        api_key: Linear API key.
        project_name: Exact Linear project name.

    Returns:
        Linear project id.

    Raises:
        RuntimeError: If no project matches the name.
    """
    payload = {
        "query": _FIND_PROJECT_QUERY,
        "variables": {"name": project_name},
    }
    data = linear_graphql(url, api_key, payload)
    nodes = data.get("data", {}).get("projects", {}).get("nodes") or []
    if not nodes or not nodes[0].get("id"):
        raise RuntimeError(f"Could not find Linear project: {project_name}")
    project_id: str = nodes[0]["id"]
    return project_id


def create_milestone(
    url: str,
    api_key: str,
    project_id: str,
    name: str,
    description: str,
) -> dict:
    """
    Create a Linear project milestone.

    Parameters:
        url: Linear GraphQL endpoint.
        api_key: Linear API key.
        project_id: Target Linear project id.
        name: Milestone title.
        description: Milestone body text.

    Returns:
        The projectMilestoneCreate payload from the API response.

    Raises:
        RuntimeError: If the mutation does not succeed.
    """
    payload = {
        "query": _CREATE_MILESTONE_MUTATION,
        "variables": {
            "projectId": project_id,
            "name": name,
            "description": description,
        },
    }
    data = linear_graphql(url, api_key, payload)
    result = data.get("data", {}).get("projectMilestoneCreate")
    if not result or not result.get("success"):
        raise RuntimeError(f"projectMilestoneCreate failed: {json.dumps(result)}")
    return result


def main() -> None:
    """Entry point for CLI execution."""
    args = parse_args()
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        print("ERROR: LINEAR_API_KEY is required", file=sys.stderr)
        sys.exit(1)

    archive = find_chart_archive(args.workspace)
    beta_version = extract_chart_version(archive)
    project_id = find_project_id(args.graphql_url, api_key, args.project_name)
    print(f"Found project ID: {project_id}")

    release_dt = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    milestone_name = f"{beta_version} - {release_dt}"
    print(f"Creating Linear milestone: {milestone_name}")
    result = create_milestone(
        args.graphql_url,
        api_key,
        project_id,
        milestone_name,
        args.milestone_description,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
