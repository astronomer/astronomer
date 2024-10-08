from pathlib import Path

import yaml

# The top-level path of this repository
git_root_dir = [x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()][-1]

metadata = yaml.safe_load((Path(git_root_dir) / "metadata.yaml").read_text())
# replace all patch versions with 0 so we end up with ['a.b.0', 'x.y.0']
supported_k8s_versions = [".".join(x.split(".")[:-1] + ["0"]) for x in metadata["test_k8s_versions"]]
k8s_version_too_old = f'1.{int(supported_k8s_versions[0].split(".")[1]) - 1!s}.0'
k8s_version_too_new = f'1.{int(supported_k8s_versions[-1].split(".")[1]) + 1!s}.0'


def get_containers_by_name(doc, *, include_init_containers=False) -> dict:
    """Given a single doc, return all the containers by name.

    doc must be a valid spec for a pod manager. (EG: ds, sts)
    """

    c_by_name = {c["name"]: c for c in doc["spec"]["template"]["spec"]["containers"]}

    if include_init_containers and doc["spec"]["template"]["spec"].get("initContainers"):
        c_by_name.update({c["name"]: c for c in doc["spec"]["template"]["spec"].get("initContainers")})

    return c_by_name


def get_cronjob_containerspec_by_name(doc) -> dict:
    """Given a single doc, return all the containers by name.

    doc must be a valid spec for a CronJob.
    """

    return {c["name"]: c for c in doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]}
