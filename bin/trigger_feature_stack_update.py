#!/usr/bin/env python3
"""
This script is used to run feature_stack_release workflow from terraform-aws-astronomer.
"""

import argparse
import http.client
import json
import os
import re
import time
from pathlib import Path

CHECK_PIPELINE_STATUES_TIMER_MIN = 5
GITHUB_ORG = "astronomer"
CIRCLECI_URL = "circleci.com"
REPO = "terraform-aws-astronomer"
REPO_BRANCH = "master"

parent_directory = Path(__file__).parent.parent
circleci_directory = parent_directory / ".circleci"


def run_workflow(circleci_token: str, parameters: dict = None):
    circle_ci_conn = http.client.HTTPSConnection(CIRCLECI_URL, timeout=15)
    api_endpoint = f"/api/v2/project/github/{GITHUB_ORG}/{REPO}/pipeline"

    headers = {"content-type": "application/json", "Circle-Token": circleci_token}

    payload = {"branch": REPO_BRANCH}

    if parameters is not None:
        payload["parameters"] = parameters

    circle_ci_conn.request(
        method="POST", url=api_endpoint, body=json.dumps(payload), headers=headers
    )
    resp = circle_ci_conn.getresponse().read().decode("utf-8")
    circle_ci_conn.close()
    return resp


def get_job_state(circleci_token: str, pipeline_id: str):
    circle_ci_conn = http.client.HTTPSConnection(CIRCLECI_URL, timeout=15)
    api_endpoint = f"/api/v2/pipeline/{pipeline_id}/workflow"

    headers = {"content-type": "application/json", "Circle-Token": circleci_token}

    circle_ci_conn.request(method="GET", url=api_endpoint, headers=headers)
    resp = circle_ci_conn.getresponse().read().decode("utf-8")
    circle_ci_conn.close()
    return resp


def main(circleci_token: str, astro_path: str, branch: str):
    # Getting Astronomer Helm Chart - FileName
    file_list = os.listdir(astro_path)

    astro_version = None
    for file_name in file_list:
        x = re.search("astronomer-.*.tgz", file_name)
        if x is not None and astro_version is None:
            print(f"INFO: Found file {file_name}")
            astro_version = file_name

    if astro_version is None:
        print(
            f"INFO: Skipping calling workflow as no valid version. Below files are found at path: {astro_path}."
        )
        print(json.dumps(file_list))
        raise SystemExit(0)

    astro_version = astro_version.removeprefix("astronomer-")
    astro_version = astro_version.removesuffix(".tgz")

    parameters = {
        "astro_version": astro_version,
        "workflow_gen": True,
        "workflow_name": "feature_stack",
        "workflow_extra_params_json": json.dumps({"release": branch}),
    }

    print("INFO: Printing parameters")
    print(json.dumps(parameters, indent=1))

    # Run Workflow
    run_workflow_resp = run_workflow(
        circleci_token=circleci_token, parameters=parameters
    )

    pipeline_id = json.loads(run_workflow_resp)["id"]
    pipeline_number = json.loads(run_workflow_resp)["number"]

    # Printing Info
    print(
        f"CircleCI JOB URL = https://app.circleci.com/pipelines/github/{GITHUB_ORG}/{REPO}/{pipeline_number}"
    )

    print("INFO: Waiting until pipeline starts running. It will wait for 5 min.")
    pipeline_state = "pending"
    counter = 0

    while "pending" == pipeline_state:
        time.sleep(10)
        job_state_resp = get_job_state(
            circleci_token=circleci_token, pipeline_id=pipeline_id
        )
        pipeline_state = json.loads(job_state_resp)["items"][0]["status"]
        counter = counter + 1

        if counter == 6:
            break

    if "success" != pipeline_state and "running" != pipeline_state:
        print(f"Error: Failed to run pipeline. Last Status: {pipeline_state}")
        raise SystemError(1)
    else:
        raise SystemExit(0)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()

    # Required positional argument
    arg_parser.add_argument("--circleci_token", type=str, required=True)
    arg_parser.add_argument("--astro_path", type=str, required=True)
    arg_parser.add_argument("--branch", type=str, required=True)

    args = arg_parser.parse_args()

    main(
        astro_path=args.astro_path,
        circleci_token=args.circleci_token,
        branch=args.branch,
    )
