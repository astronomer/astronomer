#!/usr/bin/env bash

[ "$#" == 2 ] || { echo "ERROR: Must give exactly two arguments to scan." ; exit 1 ; }
[ -f /etc/os-release ] && cat /etc/os-release

GIT_ROOT="$(git -C "${0%/*}" rev-parse --show-toplevel)"
scan_target="$1"
ignore_file="$2"

set +exo pipefail

trivy \
  --cache-dir /tmp/workspace/trivy-cache \
  image \
  --ignorefile "${GIT_ROOT}/.cirleci/${ignore_file}" \
  --ignore-unfixed -s HIGH,CRITICAL \
  --exit-code 1 \
  --no-progress \
  "${scan_target}" > "${GIT_ROOT}/trivy-output.txt"
exit_code=$?

cat "${GIT_ROOT}/trivy-output.txt"

# Trivy cannot detect vulnerabilities not installed by package managers (EG: busybox, buildroot, make install):
# - https://github.com/aquasecurity/trivy/issues/481 2020-04-30
if grep -q -i 'OS is not detected' trivy-output.txt ; then
  echo "Skipping trivy scan because of unsupported OS"
  exit 0
fi

exit "${exit_code}"
