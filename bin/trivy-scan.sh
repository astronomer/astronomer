#!/usr/bin/env bash

[ "$#" == 2 ] || {
  echo "ERROR: Must give exactly two arguments: <image_to_scan> <ignore_file>"
  exit 1
}
[ -f /etc/os-release ] && cat /etc/os-release

GIT_ROOT="$(git -C "${0%/*}" rev-parse --show-toplevel)"
GIT_RELEASE="$(git symbolic-ref -q --short HEAD || git describe --tags --exact-match)"
scan_target="$1"
ignore_file="$2"

set +exo pipefail

trivy \
  --cache-dir /tmp/workspace/trivy-cache \
  image \
  -s HIGH,CRITICAL \
  --ignorefile "${GIT_ROOT}/${ignore_file}" \
  --ignore-unfixed \
  --exit-code 1 \
  --no-progress \
  --format json \
  "${scan_target}" >"${GIT_ROOT}/trivy-output.txt"
exit_code=$?

cat "${GIT_ROOT}/trivy-output.txt"

# Trivy cannot detect vulnerabilities not installed by package managers (EG: busybox, buildroot, make install):
# - https://github.com/aquasecurity/trivy/issues/481 2020-04-30
if grep -q -i 'OS is not detected' trivy-output.txt; then
  echo "Skipping the Trivy scan because of unsupported OS"
elif [ "${exit_code}" -gt 0 ]; then

  set -o xtrace

  payload=$(cat "${GIT_ROOT}/trivy-output.txt")

  curl --location --request POST "$ASTRO_SEC_ENDPOINT" \
    --header 'Content-Type: application/json' \
    --data-raw '{
      "operation": "create",
      "scanner": "trivy",
      "repo": "astronomer/astronomer",
      "release": '"\"${GIT_RELEASE}\""',
      "payload": '"${payload}"'
    }'

fi

exit "${exit_code}"
