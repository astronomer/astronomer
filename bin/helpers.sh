#!/usr/bin/env bash
# This contents of this file must be compatible with CI and local dev workflows
set -euo pipefail

function get_debugging_info {
  echo "Failed to deploy Astronomer!"
  echo "Printing description and logs where containers in pod are not 1/1..."
  for pod in $(kubectl get pods -n astronomer | grep -vE 'NAME|1/1|Completed' | awk '{ print $1 }') ; do
    echo "======================="
    ( set -x ; kubectl describe pod -n astronomer "$pod" )
    ( set -x ; kubectl logs -n astronomer "$pod" --all-containers=true | tail -n 30 )
    echo "======================="
  done
  kubectl get secrets --all-namespaces
  echo "======================="
  kubectl get pods --all-namespaces
  echo "======================="
  kubectl get ds --all-namespaces
  echo "======================="
  kubectl get sts --all-namespaces
  echo "======================="
  kubectl get deployments --all-namespaces
}
