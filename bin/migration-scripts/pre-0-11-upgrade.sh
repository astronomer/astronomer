#!/bin/bash

set -e

function check_cli_tools_installed {
  for executable in $@; do
    which $executable > /dev/null 2>&1
    if [ $? -eq 0 ]; then
      echo "$executable is in PATH"
    else
      echo "Please ensure $executable is installed and in PATH"
      exit 1
    fi
  done
}

function check_helm_version_client {
  echo "Checking the version of Helm installed on the client (where this script is executed)..."
  set +e
  helm version | grep Client | grep $1 > /dev/null
  if ! [[ $? -eq 0 ]]; then
    echo ""
    echo "==============="
    echo "Action required:"
    echo "Please install Helm 2.16.1"
    echo "Link: https://github.com/helm/helm/releases/tag/v2.16.1"
    exit 1
  else
    echo "Confirmed Helm 2.16.1 is installed."
  fi
  set -e
}

# Sanity checks to confirm some assumptions
# about the environment
function kube_checks {
  set +e
  echo "Checking kube authentication..."
  namespaces=$(kubectl get namespaces)
  if ! [[ $? -eq 0 ]]; then
    echo "Failed to run 'kubectl get namespaces'. Please check kubectl configuration."
    exit 1
  else
    echo "kubectl is installed and we can access a kube cluster."
  fi
  echo "$namespaces" | grep $NAMESPACE > /dev/null
  if ! [[ $? -eq 0 ]]; then
    echo "Failed find the namespace $NAMESPACE"
    exit 1
  else
    echo "Confirmed the presence of the namespace $NAMESPACE"
  fi
  set -e
  echo "Checking that the release $RELEASE_NAME corresponds to the namespace $NAMESPACE"
  get_namespace_of_release $RELEASE_NAME
  if ! [[ "$namespace_of_release_result" = "$NAMESPACE" ]]; then
    echo "ERROR did not find the namespace of helm release $RELEASE_NAME to be $NAMESPACE, but instead found it to be $namespace_of_release_result"
    exit 1
  else
    echo "Confirmed! Found that Helm release $RELEASE_NAME is in namespace $NAMESPACE"
  fi
}

function get_namespace_of_release {
  namespace_of_release_result=$(helm status $1 | grep -i namespace | head -n 1 | awk '{ print $2 }')
  if ! [[ $? -eq 0 ]]; then
    echo "Failed to find the namespace of release $1"
    exit 1
  fi
  kubectl get namespaces | grep "$namespace_of_release_result" > /dev/null
  if ! [[ $? -eq 0 ]]; then
    echo "Failed to find the namespace of release $1: ERROR did not find a namespace $namespace_of_release_result in Kubernetes"
    exit 1
  fi
}

function get_helm_values_of_release {
  set +e
  export values_result=$(helm get values --output json $1)
  if ! [[ $? -eq 0 ]]; then
    echo "Did not find a Helm release $1"
    exit 1
  fi
  set -e
}

function get_deployments {
  set +e
  echo "Looking for Astronomer deployments..."
  export RELEASE_NAMES=$(helm list | grep airflow | grep astronomer | awk '{ print $1 }')
  if ! [[ $? -eq 0 ]]; then
    echo "Did not find any Astronomer deployments"
    exit 1
  fi
  echo "Found Astronomer deployments."
  echo "Confirming these Helm releases are indeed Astronomer Airflow deployments..."
  for release in $RELEASE_NAMES; do
    executor=$(helm get values $release --output json | jq '.executor' | grep -E 'CeleryExecutor|KubernetesExecutor|LocalExecutor')
    if ! [[ $? -eq 0 ]]; then
      echo "Did not find an executor for $release, aborting because we expected this would be an Astronomer deployment"
      exit 1
    fi
    echo "    $release: $executor"
  done
  echo "We found an executor for all Helm release names, so we can be confident these are Astronomer Airflow deployments."
  set -e
}

function ensure_fernet_key_for_all_deployments {
  # Find all the Astronomer Airflow deployments
  get_deployments
  echo "The fernet key is a secret that is used to encrypt other secrets in the Airflow DB."
  echo "For all deployments, ensuring that we persist the fernet key..."
  for release in $RELEASE_NAMES; do
    echo "Processing $release:"
    # Get the namespace
    get_namespace_of_release $release
    echo "  Determined namespace is : $namespace_of_release_result"
    helm get $release_name > $release_name-full-backup.yaml
    # Find the secret's actual value
    fernet=$(kubectl get secret -n $namespace_of_release_result \
      ${release}-fernet-key -o jsonpath="{.data.fernet-key}" | base64 --decode)
    decoded_length=$(echo "$fernet" | base64 --decode | wc | awk '{ print $3 }')
    if ! [[ "$decoded_length" = "32" ]]; then
      echo "ERROR: expected to find a fernet key when base64 decoded to have length 32, but we found length $decoded_length"
      exit 1
    else
      echo "  Found the fernet key from the namespace"
    fi
    # Check if this matches the helm config
    get_helm_values_of_release $release
    configured_fernet=$(echo "$values_result" | jq '.fernetKey' --raw-output)
    if [[ "$configured_fernet" = "$fernet" ]]; then
      echo "  This fernet key is already configured in Helm"
    else
      echo "  Detected that the fernet key needs to be added to the Helm values."
      add_fernet_to_values $release $namespace_of_release_result $fernet
    fi
  done
}

function add_fernet_to_values {
  release_name=$1
  release_namespace=$2
  fernet_key=$3
  set -e
  get_chart_version $release_name
  echo "    Begin fernet key persistence procedure for $release_name, airflow chart version $version_result"
  helm get values $release_name > $release_name.yaml
  echo "    Upgrading helm chart."
  set -x
  helm upgrade -f ./$release_name.yaml --set fernetKey="$fernet_key" --version "$version_result" --namespace $release_namespace $release_name astronomer/airflow
  set +x
  echo "    Done."
}

function get_chart_version {
  version_result=$(helm list $1 | grep $1 | awk '{ print $9 }' | cut -d '-' -f2)
}

function main {
  export RELEASE_NAME=$1
  export NAMESPACE=$2

  # Pre-flight checks
  check_helm_version_client '2.16.1'
  check_cli_tools_installed helm kubectl jq
  kube_checks

  # Initialize helm
  helm init --client-only
  # Install airflow chart
  helm repo add astronomer https://helm.astronomer.io
  helm repo update

  ensure_fernet_key_for_all_deployments
}

main $1 $2
