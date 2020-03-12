#!/usr/bin/env bash
set -euo pipefail

function get_debugging_info {
  echo "Failed to deploy Astronomer!"
  echo "Printing description and logs where containers in pod are not 1/1..."
  for pod in $(kubectl get pods -n astronomer | grep -v NAME | grep -v 1/1 | grep -v Completed | awk '{ print $1 }'); do
    echo "======================="
    set -x
    kubectl describe pod -n astronomer $pod
    kubectl logs -n astronomer $pod | tail -n 30
    set +x
    echo "======================="
  done
  kubectl get pods --all-namespaces
  echo "======================="
  kubectl get ds --all-namespaces
  echo "======================="
  kubectl get sts --all-namespaces
  echo "======================="
  kubectl get deployments --all-namespaces
}

