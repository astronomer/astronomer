#!/usr/bin/env bash
set -e

unique_versions=$(awk '/^(version|appVersion)/ {print $2}' Chart.yaml charts/astronomer/Chart.yaml | sort -u | wc -l)

if [[ "$unique_versions" -ne 1 ]]; then
  echo "ERROR: version/appVersion mismatch between Chart.yaml and charts/astronomer/Chart.yaml"
  grep -E '^(version|appVersion)' Chart.yaml charts/astronomer/Chart.yaml
  exit 1
fi

echo "Chart versions are consistent"
