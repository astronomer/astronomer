from pathlib import Path

import yaml

# The top-level path of this repository -- the nearest ancestor holding a .git entry (a directory
# in a normal clone, a file in a linked worktree, so `.exists()` covers both). Fail fast with a
# clear message if it can't be found, rather than letting a None propagate into path strings.
git_root_dir = next((p for p in Path(__file__).resolve().parents if (p / ".git").exists()), None)
if git_root_dir is None:
    raise RuntimeError(f"Could not locate the repository root: no .git entry found above {Path(__file__).resolve()}")

chart_metadata = yaml.safe_load((git_root_dir / "metadata.yaml").read_text())
# replace all patch versions with 0 so we end up with ['a.b.0', 'x.y.0']
supported_k8s_versions = [".".join([*x.split(".")[:-1], "0"]) for x in chart_metadata["test_k8s_versions"]]
newest_supported_kube_version = supported_k8s_versions[-1]
oldest_supported_kube_version = supported_k8s_versions[0]
k8s_version_too_old = f"1.{int(supported_k8s_versions[0].split('.')[1]) - 1!s}.0"
k8s_version_too_new = f"1.{int(supported_k8s_versions[-1].split('.')[1]) + 1!s}.0"
# kubectl is one version old https://kubernetes.io/releases/version-skew-policy/#kubectl
kubectl_version = chart_metadata["test_k8s_versions"][-2]
