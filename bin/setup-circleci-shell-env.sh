#!/usr/bin/env bash
# Set up an environment for debugging in ssh to CircleCI workflows

[ "$CIRCLECI" == true ] || { echo "ERROR: not running in CircleCI" ; exit 1 ; }

STERN_VERSION=1.25.0 # https://github.com/stern/stern/releases
NAMESPACE="${NAMESPACE:-astronomer}"

cat >> "$HOME/.bashrc" <<EOF
export PATH="/tmp/bin:/tmp/google-cloud-sdk/bin:$PATH"
export NAMESPACE="${NAMESPACE:-astronomer}"
alias ka="kubectl -n ${NAMESPACE}"
alias k="kubectl"
alias k-pods="kubectl get pods --sort-by=.metadata.creationTimestamp"
EOF

curl -fsSL https://github.com/stern/stern/releases/download/v${STERN_VERSION}/stern_${STERN_VERSION}_linux_amd64.tar.gz |
    tar -xz --directory="/tmp/bin" --strip-components=1 "stern_${STERN_VERSION}_linux_amd64/stern"
