# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import json
import os
import shlex
import subprocess
from functools import cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import jsonschema
import requests
import yaml
from kubernetes.client.api_client import ApiClient

from tests import supported_k8s_versions

api_client = ApiClient()

BASE_URL_SPEC = "https://raw.githubusercontent.com/yannh/kubernetes-json-schema/refs/heads/master"
git_root_dir = [x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()][-1]
DEBUG = os.getenv("DEBUG", "").lower() in ["yes", "true", "1"]
default_version = supported_k8s_versions[-1]


def get_schema_k8s(api_version, kind, kube_version=default_version):
    """Return a standalone k8s schema for use in validation."""
    api_version = api_version.lower()
    kind = kind.lower()

    if "/" in api_version:
        ext, _, api_version = api_version.partition("/")
        ext = ext.split(".")[0]
        schema_path = f"v{kube_version}-standalone/{kind}-{ext}-{api_version}.json"
    else:
        schema_path = f"v{kube_version}-standalone/{kind}-{api_version}.json"

    local_sp = Path(f"{git_root_dir}/tests/k8s_schema/{schema_path}")
    if not local_sp.exists():
        if not local_sp.parent.is_dir():
            local_sp.parent.mkdir(parents=True)
        request = requests.get(f"{BASE_URL_SPEC}/{schema_path}", timeout=30)
        request.raise_for_status()
        local_sp.write_text(request.text)

    return json.loads(local_sp.read_text())


@cache
def create_validator(api_version, kind, kube_version=default_version):
    """Create a k8s validator for the given inputs."""
    schema = get_schema_k8s(api_version, kind, kube_version=kube_version)
    jsonschema.Draft7Validator.check_schema(schema)
    return jsonschema.Draft7Validator(schema)


def validate_k8s_object(instance, kube_version=default_version):
    """Validate the k8s object."""
    validate = create_validator(instance.get("apiVersion"), instance.get("kind"), kube_version=kube_version)
    validate.validate(instance)


def render_chart(
    *,  # require keyword args
    name: str = "release-name",
    values: dict | None = None,
    show_only: list | None = None,
    chart_dir: str | None = None,
    kube_version: str = default_version,
    baseDomain: str = "example.com",
    namespace: str | None = None,
    validate_objects: bool = True,
):
    """Render a helm chart into dictionaries."""
    values = values or {}
    chart_dir = chart_dir or str(git_root_dir)
    with NamedTemporaryFile(delete=not DEBUG) as tmp_file:  # export DEBUG=true to keep
        content = yaml.dump(values)
        tmp_file.write(content.encode())
        tmp_file.flush()
        command = [
            "helm",
            "template",
            "--kube-version",
            kube_version,
            name,
            chart_dir,
            "--set",
            f"global.baseDomain={baseDomain}",
            "--values",
            tmp_file.name,
        ]
        if namespace:
            command.extend(["--namespace", namespace])
        if show_only:
            if isinstance(show_only, str):
                show_only = [show_only]
            for file in show_only:
                command.extend(["--show-only", str(file)])

        if DEBUG:
            print(f"helm command:\n  {shlex.join(command)}")

        try:
            manifests = subprocess.check_output(command, stderr=subprocess.PIPE)
            if not manifests:
                return None
        except subprocess.CalledProcessError as error:
            if DEBUG:
                print("ERROR: subprocess.CalledProcessError:")
                print(f"Values file contents:\n{'-' * 21}\n{yaml.dump(values)}{'-' * 21}")
                print(f"{error.output=}\n{error.stderr=}")

                if "could not find template" in error.stderr.decode("utf-8"):
                    print(
                        "ERROR: command is probably using templates with null output, which "
                        + "usually means there is a helm value that needs to be set to render "
                        + "the content of the chart.\n"
                        + "command: "
                        + shlex.join(command)
                    )
            raise
        return load_and_validate_k8s_manifests(manifests, validate_objects=validate_objects, kube_version=kube_version)


def load_and_validate_k8s_manifests(manifests: str, validate_objects: bool = True, kube_version: str = default_version):
    """Load k8s objecdts from yaml into python, optionally validating them. yaml can contain multiple documents."""
    k8s_objects = [k8s_object for k8s_object in yaml.full_load_all(manifests) if k8s_object]

    if validate_objects:
        for k8s_object in k8s_objects:
            validate_k8s_object(k8s_object, kube_version=kube_version)
    return k8s_objects


def prepare_k8s_lookup_dict(k8s_objects) -> dict[tuple[str, str], dict[str, Any]]:
    """Helper to create a lookup dict from k8s_objects.

    The keys of the dict are the k8s object's kind and name
    """
    return {(k8s_object["kind"], k8s_object["metadata"]["name"]): k8s_object for k8s_object in k8s_objects}
