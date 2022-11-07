from pathlib import Path

import git

# The top-level path of this repository
git_repo = git.Repo(__file__, search_parent_directories=True)
git_root_dir = Path(git_repo.git.rev_parse("--show-toplevel"))

# This should match the major.minor version list in .circleci/generate_circleci_config.py
# Patch version should always be 0
supported_k8s_versions = ["1.21.0", "1.22.0", "1.23.0", "1.24.0"]


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
