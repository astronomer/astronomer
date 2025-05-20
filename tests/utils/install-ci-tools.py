#!/usr/bin/env python3
"""Functions to install various tools used in CI/CD pipelines.

Tools are installed into a per-user directory under ~/.local/share/astronomer-software/bin

Downloaded archives are cached in ~/.cache/astronomer-software"""

import os
import platform
import shutil
import sys
import tarfile
from pathlib import Path

import requests
import yaml

from tests import git_root_dir

KIND_VERSION = "0.27.0"
HELM_VERSION = "3.18.0"
KUBECTL_VERSION = yaml.dump((git_root_dir / "metadata.yaml").read_text())

OS = platform.system().lower()
ARCH = "amd64"

BASE_DIR = Path.home() / ".local" / "share" / "astronomer-software"
CACHE_DIR = Path.home() / ".cache" / "astronomer-software"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
BIN_DIR = BASE_DIR / "bin"
BIN_DIR.mkdir(parents=True, exist_ok=True)
os.environ["PATH"] = f"{BIN_DIR}:{os.environ['PATH']}"

FORCE = int(sys.argv[1]) if len(sys.argv) > 1 else 0


def download(url, dest, mode="wb"):
    print(f"Downloading {url} -> {dest}")
    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    with open(dest, mode) as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    os.chmod(dest, 0o700)


def install_kind():
    dest = BIN_DIR / "kind"
    if not FORCE and dest.exists():
        print("kind already installed.")
        return
    url = f"https://github.com/kubernetes-sigs/kind/releases/download/v{KIND_VERSION}/kind-{OS}-{ARCH}"
    download(url, dest)


def install_helm():
    dest = BIN_DIR / "helm"
    if not FORCE and dest.exists():
        print("helm already installed.")
        return
    tgz = CACHE_DIR / f"helm-v{HELM_VERSION}-{OS}-{ARCH}.tar.gz"
    url = f"https://get.helm.sh/helm-v{HELM_VERSION}-{OS}-{ARCH}.tar.gz"
    if not tgz.exists():
        download(url, tgz)
    with tarfile.open(tgz, "r:gz") as tar:
        member = tar.getmember(f"{OS}-{ARCH}/helm")
        member.name = "helm"  # avoid path traversal
        tar.extract(member, BIN_DIR, filter="data")
        shutil.move(str(BIN_DIR / "helm"), dest)


def install_kubectl():
    dest = BIN_DIR / "kubectl"
    if not FORCE and dest.exists():
        print("kubectl already installed.")
        return
    url_version = "https://storage.googleapis.com/kubernetes-release/release/stable.txt"
    version = requests.get(url_version, timeout=5).text.strip()
    url = f"https://storage.googleapis.com/kubernetes-release/release/{version}/bin/{OS}/amd64/kubectl"
    download(url, dest)


def main():
    install_kind()
    install_helm()
    install_kubectl()
    print(f"All tools installed in {BIN_DIR}")


if __name__ == "__main__":
    main()
