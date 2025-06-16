#!/usr/bin/env python3
"""Generate default container probes YAML for testing purposes.

This script runs `helm template` on the current chart with all features enabled,
and extracts the liveness and readiness probes from the generated Kubernetes manifests.
The output is saved in the `tests/chart_tests/test_data/` directory.

This specifically does *NOT* have a pre-commit hook attached to it because that would
cause it to "fix" any probes that were broken during development. This should only be run
when you know for sure that there are default probes changes that need to be tested.
"""

from pathlib import Path
import subprocess

import yaml

git_root_dir = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)


def run_helm_template():
    values_file = f"{git_root_dir}/tests/enable_all_features.yaml"
    cmd = [
        "helm",
        "template",
        "--set",
        "forceIncompatibleKubernetes=True",
        "--generate-name",
        str(git_root_dir),
        "--values",
        values_file,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def parse_templates(yaml_str):
    return list(yaml.safe_load_all(yaml_str))


def get_pod_specs(doc):
    """
    Returns [(podname, containers)] for resources that have pod templates.
    Supports Pod, Deployment, StatefulSet, DaemonSet, ReplicaSet, etc.
    """
    if not doc:
        return []
    kind = doc.get("kind")
    metadata = doc.get("metadata", {})
    name = metadata.get("name", "unknown")
    spec = doc.get("spec", {})

    # Direct Pod
    if kind == "Pod" and "containers" in spec:
        return [(name, spec["containers"])]
    # Controller with template
    template = spec.get("template", {}).get("spec", {})
    if "containers" in template:
        return [(name, template["containers"])]
    return []


def extract_probe_dict(docs, probe_type):
    """
    probe_type: 'livenessProbe' or 'readinessProbe'
    Returns dict of podname_containername: probe_definition
    """
    probe_map = {}
    for doc in docs:
        pod_specs = get_pod_specs(doc)
        for podname, containers in pod_specs:
            podname = podname.removeprefix("release-name-")
            for container in containers:
                cname = container.get("name")
                probe = container.get(probe_type)
                if cname and probe:
                    key = f"{podname}_{cname}"
                    probe_map[key] = probe
    return probe_map


def main():
    helm_yaml = run_helm_template()
    docs = parse_templates(helm_yaml)

    liveness_probes = extract_probe_dict(docs, "livenessProbe")
    readiness_probes = extract_probe_dict(docs, "readinessProbe")

    with open(f"{git_root_dir}/tests/chart_tests/test_data/default_container_readiness_probes.yaml", "w") as f:
        f.write("# Each key here is a pod_container.\n\n")
        f.write(yaml.safe_dump(readiness_probes, sort_keys=True, default_flow_style=False))
    with open(f"{git_root_dir}/tests/chart_tests/test_data/default_container_liveness_probes.yaml", "w") as f:
        f.write("# Each key here is a pod_container.\n\n")
        f.write(yaml.safe_dump(liveness_probes, sort_keys=True, default_flow_style=False))


if __name__ == "__main__":
    main()
