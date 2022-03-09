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

import subprocess
import sys
from functools import cache
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Tuple
from pathlib import Path
from typing import Optional

import jsonschema
import requests
import yaml
from kubernetes.client.api_client import ApiClient

api_client = ApiClient()

BASE_URL_SPEC = "https://raw.githubusercontent.com/yannh/kubernetes-json-schema/master"


# TODO: make this cache the schema so we can test offline, or better, save these to the tests dir
@cache
def get_schema_k8s(api_version, kind, kube_version="1.21.0"):
    """Return a k8s schema for use in validation."""
    api_version = api_version.lower()
    kind = kind.lower()

    if "/" in api_version:
        ext, _, api_version = api_version.partition("/")
        ext = ext.split(".")[0]
        url = f"{BASE_URL_SPEC}/v{kube_version}-standalone/{kind}-{ext}-{api_version}.json"
    else:
        url = f"{BASE_URL_SPEC}/v{kube_version}-standalone/{kind}-{api_version}.json"
    request = requests.get(url)
    request.raise_for_status()
    return request.json()


@cache
def create_validator(api_version, kind, kube_version="1.21.0"):
    """Create a k8s validator for the given inputs."""
    schema = get_schema_k8s(api_version, kind, kube_version=kube_version)
    jsonschema.Draft7Validator.check_schema(schema)
    return jsonschema.Draft7Validator(schema)


def validate_k8s_object(instance, kube_version="1.21.0"):
    """Validate the k8s object."""
    validate = create_validator(
        instance.get("apiVersion"), instance.get("kind"), kube_version=kube_version
    )
    validate.validate(instance)


def render_chart(
    name: str = "release-name",
    values: Optional[dict] = None,
    show_only: Optional[list] = None,
    chart_dir: Optional[str] = None,
    kube_version: str = "1.21.0",
    baseDomain: str = "example.com",
    namespace: Optional[str] = None,
):
    """
    Render a helm chart into dictionaries. For helm chart testing only.
    """
    values = values or {}
    chart_dir = chart_dir or sys.path[0]
    with NamedTemporaryFile() as tmp_file:
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
            for i in show_only:
                if not Path(i).exists():
                    raise FileNotFoundError(f"ERROR: {i} not found")
                else:
                    command.extend(["--show-only", i])
        try:
            templates = subprocess.check_output(command, stderr=subprocess.PIPE)
            if not templates:
                return None
        except subprocess.CalledProcessError as error:
            print("ERROR: subprocess.CalledProcessError:")
            print(f"helm command: {' '.join(command)}")
            print(f"Values file contents:\n{'-' * 21}\n{yaml.dump(values)}{'-' * 21}")
            print(f"{error.output=}\n{error.stderr=}")

            if "could not find template" in error.stderr.decode("utf-8"):
                print(
                    "ERROR: command is probably using templates with null output, which "
                    + "usually means there is a helm value that needs to be set to render "
                    + "the content of the chart.\n"
                    + "command: "
                    + " ".join(command)
                )
            raise
        k8s_objects = yaml.full_load_all(templates)
        k8s_objects = [k8s_object for k8s_object in k8s_objects if k8s_object]  # type: ignore
        for k8s_object in k8s_objects:
            validate_k8s_object(k8s_object, kube_version=kube_version)
        return k8s_objects


def prepare_k8s_lookup_dict(k8s_objects) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """
    Helper to create a lookup dict from k8s_objects.
    The keys of the dict are the k8s object's kind and name
    """
    return {
        (k8s_object["kind"], k8s_object["metadata"]["name"]): k8s_object
        for k8s_object in k8s_objects
    }


def render_k8s_object(obj, type_to_render):
    """
    Function that renders dictionaries into k8s objects. For helm chart testing only.
    """
    return api_client._ApiClient__deserialize_model(obj, type_to_render)
