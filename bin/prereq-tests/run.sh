#!/usr/bin/env bash
set -euo pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Check for BATS
set +e
BATS=$(which bats)
if [[ $? != 0 ]]; then
  echo
  echo "ERROR: The prereq tests requires bats-core testing framework. (https://github.com/bats-core/bats-core#installation)"
  echo
  exit 1
fi
set -e

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
  echo ""
  echo "  -h    Print this help message"
  echo ""
}

# Flag processing
T_TOOLS=
T_AWS=
T_GCP=
T_K8S=

while getopts "TAGKh" OPTION; do
  case "${OPTION}" in
    T) T_TOOLS=1 ;;
    A) T_AWS=1 ;;
    G) T_GCP=1 ;;
    K) T_K8S=1 ;;

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
  echo "Tools Tests:"
  $DIR/tools.bats
  echo
  echo
fi

if [[ $T_AWS ]]; then
  echo "AWS Tests:"
  $DIR/aws.bats
  echo
  echo
fi

if [[ $T_GCP ]]; then
  echo "GCP Tests:"
  $DIR/gcp.bats
  echo
  echo
fi

if [[ $T_K8S ]]; then
  echo "Kubernets Tests:"
  $DIR/k8s.bats
  echo
  echo
fi

echo "Done checking Astronomer prereqs"

