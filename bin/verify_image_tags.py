#!/usr/bin/env python
"""Verify that every image has only one tag version."""

import subprocess
from pathlib import Path


GIT_ROOT = next(
    iter([x for x in Path(__file__).resolve().parents if (x / ".git").is_dir()]), None
)
command = "helm template . --set forceIncompatibleKubernetes=true -f tests/enable_all_features.yaml | grep -o 'quay.io/astronomer[^\"]*' | sort -u"

result = subprocess.run(
    command,
    shell=True,
    cwd=GIT_ROOT,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

if result.returncode != 0:
    print(f"Error running the command:\n{result.stderr}")
    raise SystemExit(1)

output_lines = result.stdout.strip().split("\n")

image_dict = {}
images_with_multiple_tags = []

for line in output_lines:
    if ":" not in line:
        continue

    image = line.strip()
    parts = image.rsplit(":", 1)
    image_name = parts[0]
    tag = parts[1].strip(" \"'\t\n\r")

    if image_name not in image_dict:
        image_dict[image_name] = []

    if tag and tag not in image_dict[image_name]:
        image_dict[image_name].append(tag)

for image, tags in image_dict.items():
    if len(tags) > 1:
        print(f"ERROR: image {image} has multiple tags: {', '.join(tags)}")

if any(len(tags) > 1 for tags in image_dict.values()):
    raise SystemExit(1)
