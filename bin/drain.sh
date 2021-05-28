#!/usr/bin/env bash

cat <<EOF
Run the following commands to drain:

    kubectl uncordon kind-worker
    kubectl cordon kind-worker2
    kubectl drain --force --delete-local-data --ignore-daemonsets kind-worker2

EOF
