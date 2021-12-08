from pathlib import Path
import git

# The top-level path of this repository
git_repo = git.Repo(__file__, search_parent_directories=True)
git_root_dir = Path(git_repo.git.rev_parse("--show-toplevel"))

# This list should match what is supported by 0.23, however we are currently not testing k8s 1.16 because it's deprecated everywhere.
# Patch version should always be 0
# k8s 1.19 is not supported in release 0.23, but we test it due to some upgrade edge cases
# k8s 1.16 is supported in astronomer 0.23, but it is no longer available in any cloud provider, so we do not test it in CI
supported_k8s_versions = ["1.17.0", "1.18.0", "1.19.11"]
