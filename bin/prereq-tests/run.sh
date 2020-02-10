#!/usr/bin/env bash
set -uo pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Check for BATS
BATS=$(which bats)
if [[ $? != 0 ]]; then
  echo
  echo "ERROR: The prereq tests requires bats-core testing framework. (https://github.com/bats-core/bats-core#installation)"
  echo
  exit 1
fi

# Usage string
USAGE () {
  echo "./run.sh [flags]"
  echo ""
  echo "The following flags enable tests."
  echo ""
  echo "  -T    Tools tests"
  echo "  -A    AWS tests"
  echo "  -G    GCP tests"
  echo "  -K    Kubernetes tests"
  echo "  -D    Database tests"
  echo "  -E    Other External resource tests"
  echo ""
  echo "  -h    Print this help message"
  echo ""
}

# Flag processing
T_TOOLS=
T_AWS=
T_GCP=
T_K8S=
T_DB=
T_EXT=

while getopts "TAGKDEh" OPTION; do
  case "${OPTION}" in
    T) T_TOOLS=1 ;;
    A) T_AWS=1 ;;
    G) T_GCP=1 ;;
    K) T_K8S=1 ;;
    D) T_DB=1 ;;
    E) T_EXT=1 ;;

    h)
      USAGE
      exit 0
      ;;

    *)
      echo "unknown flag '$OPTION'"
      exit 1
      ;;
  esac
done
shift $((OPTIND - 1))


# Run the enabled tests
echo
echo "Starting Astronomer prereqs tests"
echo
echo

if [[ $T_TOOLS ]]; then
  echo "User Tools:"
  $DIR/tools/user.bats
  echo
  echo
  echo "Admin Tools:"
  $DIR/tools/admin.bats
  echo
  echo
fi

if [[ $T_AWS ]]; then
  echo "AWS Base:"
  $DIR/aws/base.bats
  echo
  echo

  echo "AWS Permsissions:"
  $DIR/aws/perms.bats
  echo
  echo
fi

if [[ $T_GCP ]]; then
  echo "GCP Base:"
  $DIR/gcp/base.bats
  echo
  echo
fi

if [[ $T_DB ]]; then
  echo "Database:"
  $DIR/db/base.bats
  echo
  echo
fi

if [[ $T_K8S ]]; then
  echo "Kubernetes Base:"
  $DIR/k8s/base.bats
  echo
  echo
  echo "Kubernetes Permissions:"
  $DIR/k8s/perms.bats
  echo
  echo
  echo "Kubernetes Features:"
  $DIR/k8s/features.bats
  echo
  echo
fi

if [[ $T_EXT ]]; then
  echo "DNS and TLS:"
  $DIR/extern/domain.bats
  echo
  echo
fi

echo "Done checking Astronomer prereqs"

