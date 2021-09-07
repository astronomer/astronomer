from pathlib import Path
import git

# The top-level path of this repository
git_repo = git.Repo(__file__, search_parent_directories=True)
git_root_dir = Path(git_repo.git.rev_parse("--show-toplevel"))

# This should match the major.minor version list in .circleci/generate_circleci_config.py
# Patch version should always be 0
supported_k8s_versions = ["1.17.0", "1.18.0", "1.19.0", "1.20.0", "1.21.0"]
