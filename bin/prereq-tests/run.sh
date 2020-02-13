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
  echo "  -D    Database tests"
  echo "  -K    Kubernetes tests"
  echo "  -P    Astronomer Platform tests"
  echo "  -E    Other External resource tests"
  echo ""
  echo "  -h    Print this help message"
  echo ""
}

# Flag processing
T_TOOLS=
T_AWS=
T_GCP=
T_DB=
T_K8S=
T_AP=
T_EXT=

if [[ -z $@ ]]; then
  echo "error: no flags provided"
  echo
  USAGE
  exit 1
fi

while getopts "TAGDKPEh" OPTION; do
  case "${OPTION}" in
    T) T_TOOLS=1 ;;
    A) T_AWS=1 ;;
    G) T_GCP=1 ;;
    D) T_DB=1 ;;
    K) T_K8S=1 ;;
    P) T_AP=1 ;;
    E) T_EXT=1 ;;

    h)
      USAGE
      exit 0
      ;;

    *)
      echo "error: unknown flag '$OPTION'"
      echo
      USAGE
      exit 1
      ;;
  esac
done
shift $((OPTIND - 1))


run_test () {
  BATS=$1
  TITLE=$2

  # The echoes help with output separation
  echo "$TITLE"
  $BATS
  echo
  echo
}

# Run the enabled tests
echo
echo "Starting Astronomer prereqs tests"
echo
echo

if [[ $T_TOOLS ]]; then
  run_test $DIR/tools/user.bats "User Tools:"
  run_test $DIR/tools/admin.bats "Admin Tools:"
fi

if [[ $T_AWS ]]; then
  run_test $DIR/aws/base.bats "AWS Base:"
  run_test $DIR/aws/perms.bats "AWS Permsissions:"
fi

if [[ $T_GCP ]]; then
  run_test $DIR/gcp/base.bats "GCP Base:"
fi

if [[ $T_DB ]]; then
  run_test $DIR/db/base.bats "Database:"
fi

if [[ $T_K8S ]]; then
  run_test $DIR/k8s/base.bats "Kubernetes Base:"
  run_test $DIR/k8s/perms.bats "Kubernetes Permissions:"
  run_test $DIR/k8s/features.bats "Kubernetes Features:"
  run_test $DIR/k8s/astro.bats "Astronomer Prep:"
fi

if [[ $T_AP ]]; then
  run_test $DIR/platform/system.bats "Astronomer System Components:"
  run_test $DIR/platform/astro.bats "Astronomer Platform Components:"
  run_test $DIR/platform/access.bats "Astronomer Platform Access:"
fi

if [[ $T_EXT ]]; then
  run_test $DIR/extern/domain.bats "DNS and TLS:"
fi

echo "Done checking Astronomer prereqs"

