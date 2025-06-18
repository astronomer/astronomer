from pathlib import Path

import yaml

from tests.utils.chart import render_chart


def get_env_vars_dict(container_env):
    """
    Convert container environment variables list to a dictionary.
    Args:
        container_env: List of environment variable dictionaries from container spec
    Returns:
        Dictionary mapping env var names to their values or valueFrom references
    """
    return {x["name"]: x["value"] if x.get("value") else x["valueFrom"] for x in container_env}


def get_service_ports_by_name(doc):
    """Given a single service doc, return all the ports by name."""

    return {port_config["name"]: port_config for port_config in doc["spec"]["ports"]}


def get_containers_by_name(doc: dict, *, include_init_containers=False) -> dict:
    """Given a single doc, return all the containers by name.

    doc must be a valid spec for a pod manager. (EG: ds, sts, cronjob, etc.)
    """

    match doc["kind"]:
        case "Deployment" | "StatefulSet" | "ReplicaSet" | "DaemonSet" | "Job":
            containers = doc["spec"]["template"]["spec"].get("containers", [])
            initContainers = doc["spec"]["template"]["spec"].get("initContainers", [])
        case "CronJob":
            containers = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"].get("containers", [])
            initContainers = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"].get("initContainers", [])
        case _:
            raise ValueError(f"Unhandled kind: {doc['kind']}")

    c_by_name = {c["name"]: c for c in containers}

    if include_init_containers and initContainers:
        c_by_name.update({c["name"]: c for c in initContainers})

    return c_by_name


def get_service_account_name_from_doc(doc: dict, *, include_init_containers=False) -> dict:
    """Return the serviceAccountName used by the pod manager."""

    if doc["kind"] in ["Deployment", "StatefulSet", "ReplicaSet", "DaemonSet", "Job"]:
        return doc["spec"]["template"]["spec"].get("serviceAccountName")
    if doc["kind"] == "CronJob":
        return doc["spec"]["jobTemplate"]["spec"]["template"]["spec"].get("serviceAccountName")
    return None


def dot_notation_to_dict(dotted_string, default_value=None):
    """Return a dotted string for a nested dict structure where the deepest values is assigned to None or the given default.

    Example:
        dot_notation_to_dict("a.b.c.d.e", default_value=0)
        # returns {'a': {'b': {'c': {'d': {'e': 0}}}}}
    """
    parts = dotted_string.partition(".")
    if parts[2]:
        return {parts[0]: dot_notation_to_dict(parts[2], default_value=default_value)}
    return {parts[0]: default_value}


def get_all_features():
    return yaml.safe_load((Path(__file__).parent.parent / "enable_all_features.yaml").read_text())


def get_chart_containers(
    k8s_version: str,
    chart_values: dict,
    *,  # force the remaining arguments to be keyword-only
    exclude_kinds: list[str] | None = None,
    include_kinds: list[str] | None = None,
) -> dict:
    """Return a dict of pod container and initContainer specs in the form of
    {k8s_version}_{release_name}-{pod_name}_{container_name}, with some additional metadata."""

    docs = render_chart(
        kube_version=k8s_version,
        values=chart_values,
    )

    specs = [
        {
            "name": doc.get("metadata", {}).get("name"),
            "kind": doc.get("kind"),
            "containers": doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []),
            "initContainers": doc.get("spec", {}).get("template", {}).get("spec", {}).get("initContainers", []),
        }
        for doc in docs
        if "spec" in doc
        and "template" in doc["spec"]
        and "spec" in doc["spec"]["template"]
        and ("containers" in doc["spec"]["template"]["spec"] or "initContainers" in doc["spec"]["template"]["spec"])
    ]

    if exclude_kinds:
        exclude_kinds = [kind.lower() for kind in exclude_kinds]
        specs = [spec for spec in specs if spec["kind"].lower() not in exclude_kinds]

    if include_kinds:
        include_kinds = [kind.lower() for kind in include_kinds]
        specs = [spec for spec in specs if spec["kind"].lower() in include_kinds]

    return {
        f"{k8s_version}_{spec['name']}_{container['name']}": {
            **container,
            "key": f"{k8s_version}_{spec['name']}_{container['name']}",
            "kind": spec["kind"],
        }
        for spec in specs
        for container in [*spec["containers"], *spec["initContainers"]]
    }
