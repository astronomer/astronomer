#!/usr/bin/env bash
set -euo pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
REPO_DIR=$DIR/../..

echo "Creating E2E pod..."

kubectl create pod -n astronomer \
  -f $DIR/e2e-pod.yaml

helm test astronomer
