#!/usr/bin/env bash
set -euo pipefail

function hr {
  echo "======================="
}

function get_debugging_info {
  echo "Failed to deploy Astronomer!"
  echo "Printing description and logs where containers in pod are not 1/1..."
  for pod in $(kubectl get pods -n astronomer -o name | grep -vE 'NAME|Completed| ([0-9]+)/\1 ') ; do
    hr
    set -x
    kubectl describe -n astronomer "$pod"
    kubectl logs -n astronomer "$pod" --all-containers=true | tail -n 30
    set +x
    hr
  done
  kubectl get secrets --all-namespaces
  hr
  kubectl get pods --all-namespaces
  hr
  kubectl get ds --all-namespaces
  hr
  kubectl get sts --all-namespaces
  hr
  kubectl get deployments --all-namespaces
  hr
  docker exec kind-control-plane crictl images
}
