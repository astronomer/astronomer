#!/usr/bin/env python3
"""Discover current git repository state and merge this information into metadata.yaml"""


import datetime
import subprocess
import yaml
import os


def get_repo_state() -> dict:
    """Return a dict with the current repo state."""
    repo_state = {
        "git_branch": subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"]).decode("utf-8").strip(),
        "git_origin": subprocess.check_output(["git", "config", "--get", "remote.origin.url"]).decode("utf-8").strip(),
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip(),
        "build_date_iso8601": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
    }

    for var in ["CIRCLE_BUILD_URL", "CIRCLE_BUILD_NUM", "CIRCLE_REPOSITORY_URL", "CIRCLE_SHA1", "CIRCLE_WORKFLOW_ID", "CIRCLE_JOB"]:
        if os.getenv(var):
            repo_state[var] = os.getenv(var)

    helm_path = subprocess.check_output(["which helm"], shell=True).decode("utf-8").strip()
    repo_state["helm_path"] = helm_path

    helm_version = subprocess.check_output(["helm version --short"], shell=True).decode("utf-8").strip()
    repo_state["helm_version"] = helm_version

    return repo_state


def write_repo_state(repo_state):
    """Write repo_state into metadata.yaml"""
    with open("metadata.yaml") as f:
        metadata = yaml.safe_load(f)

    metadata["repo_build_state"] = repo_state

    with open("metadata.yaml", "w") as f:
        yaml.dump(metadata, f)


write_repo_state(get_repo_state())
