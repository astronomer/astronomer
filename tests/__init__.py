from pathlib import Path

import git
# The top-level path of this repository
import yaml
from yaml import SafeLoader

git_repo = git.Repo(__file__, search_parent_directories=True)
git_root_dir = Path(git_repo.git.rev_parse("--show-toplevel"))

# This should match the major.minor version list in .circleci/generate_circleci_config.py
# Patch version should always be 0
supported_k8s_versions = ["1.19.0", "1.20.0", "1.21.0", "1.22.0", "1.23.0"]


def get_containers_by_name(doc, include_init_containers=False):
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


def k8s_versions_with_all_features():
    file_path = str(Path(__file__).parent) + '/enable_all_features.yaml'

    configs = []
    with open(file_path) as f:
        feature_data = yaml.load(f, Loader=SafeLoader)

    for k8s_version in supported_k8s_versions:
        configs.append({
            "k8s_version": k8s_version,
            "values": feature_data
        })

    return configs
