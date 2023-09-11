from pathlib import Path

import yaml

# The top-level path of this repository
git_root_dir = [x for x in Path(".").resolve().parents if (x / ".git").is_dir()][
    -1
].as_posix()

metadata = yaml.safe_load((Path(git_root_dir) / "metadata.yaml").read_text())
# replace all patch versions with 0 so we end up with ['1.26.0', '1.27.0']
supported_k8s_versions = [
    ".".join(x.split(".")[:-1] + ["0"]) for x in metadata["test_k8s_versions"]
]
k8s_version_too_old = f'1.{str(int(supported_k8s_versions[0].split(".")[1]) - 1)}.0'
k8s_version_too_new = f'1.{str(int(supported_k8s_versions[-1].split(".")[1]) + 1)}.0'


def get_containers_by_name(doc, include_init_containers=False) -> dict:
    """Given a single doc, return all the containers by name.

    doc must be a valid spec for a pod manager. (EG: ds, sts)
    """

    c_by_name = {c["name"]: c for c in doc["spec"]["template"]["spec"]["containers"]}

    if include_init_containers and doc["spec"]["template"]["spec"].get(
        "initContainers"
    ):
        c_by_name.update(
            {
                c["name"]: c
                for c in doc["spec"]["template"]["spec"].get("initContainers")
            }
        )

    return c_by_name
