from pathlib import Path

import yaml

# The top-level path of this repository
git_root_dir = [x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()][-1]

chart_metadata = yaml.safe_load((Path(git_root_dir) / "metadata.yaml").read_text())
# replace all patch versions with 0 so we end up with ['a.b.0', 'x.y.0']
supported_k8s_versions = [".".join([*x.split(".")[:-1], "0"]) for x in chart_metadata["test_k8s_versions"]]
newest_supported_kube_version = supported_k8s_versions[-1]
oldest_supported_kube_version = supported_k8s_versions[0]
k8s_version_too_old = f"1.{int(supported_k8s_versions[0].split('.')[1]) - 1!s}.0"
k8s_version_too_new = f"1.{int(supported_k8s_versions[-1].split('.')[1]) + 1!s}.0"
# kubectl is one version old https://kubernetes.io/releases/version-skew-policy/#kubectl
kubectl_version = chart_metadata["test_k8s_versions"][-2]
