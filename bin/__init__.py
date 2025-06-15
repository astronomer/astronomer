import os
from pathlib import Path

import yaml

GIT_ROOT_DIR = next(iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None)
KIND_EXE = Path.home() / ".local" / "share" / "astronomer-software" / "bin" / "kind"
CHART_METADATA = yaml.safe_load((Path(GIT_ROOT_DIR) / "metadata.yaml").read_text())
KUBECTL_VERSION = CHART_METADATA["test_k8s_versions"][-2]
DEBUG = os.getenv("DEBUG", "").lower() in ["yes", "true", "1"]
