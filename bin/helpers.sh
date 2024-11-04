#!/usr/bin/env bash
set -euo pipefail

namespace="${NAMESPACE:-astronomer}"

function hr {
  echo "======================="
}

function get_debugging_info {
  echo "Failed to deploy Astronomer!"
  echo "Printing description and logs where containers in pod are not 1/1..."
  for pod in $(kubectl -n "${namespace}" get pods | grep -vE 'NAME|Completed| ([0-9]+)/\1 ' | awk '{print $1}') ; do
    hr
    bash -xc "kubectl describe -n '${namespace}' pod '${pod}'"
    bash -xc "kubectl logs -n '${namespace}' '${pod}' --all-containers=true | tail -n 30"
    hr
  done
  kubectl get events,secrets,svc,ds,sts,deployments,pods -A
  docker exec kind-control-plane crictl images
  helm list -n "${namespace}" -o json |
    jq -r '.[] | "\(.namespace) \(.name)"' |
    xargs -t -L1 helm get values -o yaml -n
}
