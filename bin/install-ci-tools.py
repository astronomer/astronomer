#!/usr/bin/env python3
"""Install various tools used in CI/CD pipelines."""

import os
import platform
import shutil
import subprocess
import tarfile
from pathlib import Path

import requests
import yaml

GIT_ROOT_DIR = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)
CHART_METADATA = yaml.safe_load((Path(GIT_ROOT_DIR) / "metadata.yaml").read_text())
KUBECTL_VERSION = CHART_METADATA["test_k8s_versions"][-2]


HELM_VERSION = CHART_METADATA["tools"]["helm"]["version"]
KIND_VERSION = CHART_METADATA["tools"]["kind"]["version"]
MKCERT_VERSION = CHART_METADATA["tools"]["mkcert"]["version"]

HELPER_DIR = Path.home() / ".local" / "share" / "astronomer-software"
CACHE_DIR = Path.home() / ".cache" / "astronomer-software"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
BIN_DIR = HELPER_DIR / "bin"
BIN_DIR.mkdir(parents=True, exist_ok=True)
os.environ["PATH"] = f"{BIN_DIR}:{os.environ['PATH']}"


def detect_os_arch():
    # Normalize OS name
    os_map = {
        "linux": "linux",
        "darwin": "darwin",
        "windows": "windows",  # Add if you want to support Windows
    }
    system = platform.system().lower()
    os_name = os_map.get(system)
    if os_name is None:
        raise RuntimeError(f"Unsupported OS: {system}")

    # Normalize architecture
    arch_map = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
    machine = platform.machine().lower()
    arch = arch_map.get(machine)
    if arch is None:
        raise RuntimeError(f"Unsupported architecture: {machine}")

    return os_name, arch


OS, ARCH = detect_os_arch()


def download(url, dest, mode="wb"):
    print(f"Downloading {url} -> {dest}")
    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    with open(dest, mode) as f:
        f.writelines(resp.iter_content(chunk_size=8192))
    os.chmod(dest, 0o700)


def install_helm():
    """Ensure that the desired version of helm is installed."""
    dest = BIN_DIR / "helm"
    if dest.exists():
        # Check the installed version
        installed_version = subprocess.run(["helm", "version", "--short"], capture_output=True, text=True)
        if HELM_VERSION in installed_version.stdout:
            print("helm already installed.")
            return
        dest.unlink()
    tgz = CACHE_DIR / f"helm-v{HELM_VERSION}-{OS}-{ARCH}.tar.gz"
    # https://github.com/helm/helm/releases
    # ['linux', 'darwin'], ['amd64', 'arm64']
    url = f"https://get.helm.sh/helm-v{HELM_VERSION}-{OS}-{ARCH}.tar.gz"
    if not tgz.exists():
        download(url, tgz)
    with tarfile.open(tgz, "r:gz") as tar:
        member = tar.getmember(f"{OS}-{ARCH}/helm")
        member.name = "helm"  # avoid path traversal
        tar.extract(member, BIN_DIR, filter="data")
        shutil.move(str(BIN_DIR / "helm"), dest)


def install_kind():
    """Ensure that the desired version of kind is installed."""
    dest = BIN_DIR / "kind"
    if dest.exists():
        # Check the installed version
        installed_version = subprocess.run(["kind", "version"], capture_output=True, text=True)
        if KIND_VERSION in installed_version.stdout:
            print("kind already installed.")
            return
        dest.unlink()
    # https://github.com/kubernetes-sigs/kind/releases
    # ['linux', 'darwin'], ['amd64', 'arm64']
    url = f"https://github.com/kubernetes-sigs/kind/releases/download/v{KIND_VERSION}/kind-{OS}-{ARCH}"
    download(url, dest)


def install_kubectl():
    """Ensure that the desired version of kubectl is installed."""
    dest = BIN_DIR / "kubectl"
    if dest.exists():
        # Check the installed version
        installed_version = subprocess.run(["kubectl", "version", "--client"], capture_output=True, text=True)
        if KUBECTL_VERSION in installed_version.stdout:
            print("kubectl already installed.")
            return
        dest.unlink()
    # ['linux', 'darwin'], ['amd64', 'arm64']
    url = f"https://dl.k8s.io/release/v{KUBECTL_VERSION}/bin/{OS}/{ARCH}/kubectl"
    download(url, dest)


def install_mkcert():
    """Ensure that the desired version of mkcert is installed."""
    dest = BIN_DIR / "mkcert"
    if dest.exists():
        # Check the installed version
        installed_version = subprocess.run(["mkcert", "--version"], capture_output=True, text=True)
        if MKCERT_VERSION in installed_version.stdout:
            print("mkcert already installed.")
            return
        dest.unlink()
    # ['linux', 'darwin'], ['amd64', 'arm64']
    url = f"https://github.com/FiloSottile/mkcert/releases/download/v{MKCERT_VERSION}/mkcert-v{MKCERT_VERSION}-{OS}-{ARCH}"
    download(url, dest)


def install_all_tools():
    """Single function to install all tools, so we can import it into pytest env setup."""
    install_helm()
    install_kind()
    install_kubectl()
    install_mkcert()
    print(f"All tools installed in {BIN_DIR}")


def main():
    install_all_tools()


if __name__ == "__main__":
    main()
