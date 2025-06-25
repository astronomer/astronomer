from pathlib import Path

import yaml

# The top-level path of this repository
git_root_dir = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)

metadata = yaml.safe_load((Path(git_root_dir) / "metadata.yaml").read_text())
# replace all patch versions with 0 so we end up with ['a.b.0', 'x.y.0']
supported_k8s_versions = [".".join(x.split(".")[:-1] + ["0"]) for x in metadata["test_k8s_versions"]]
k8s_version_too_old = f"1.{int(supported_k8s_versions[0].split('.')[1]) - 1!s}.0"
k8s_version_too_new = f"1.{int(supported_k8s_versions[-1].split('.')[1]) + 1!s}.0"


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
    """Return a dotted string for a nested dict structure where the deepest values is assigned to None or the given default."""
    parts = dotted_string.partition(".")
    if parts[2]:
        return {parts[0]: dot_notation_to_dict(parts[2])}
    return {parts[0]: default_value}
