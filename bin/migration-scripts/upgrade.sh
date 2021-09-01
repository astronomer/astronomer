#!/bin/bash

backup_dir=helm-values-backup

function fail_with {
  if [ $? -ne 0 ]; then
    echo $1
    exit 1
  fi
}

function get_chart_version {
  version_result=$(helm list $1 | grep $1 | awk '{ print $9 }' | cut -d '-' -f2)
  fail_with 'failed to list chart'
}

# this is a temporary workaround
function upgrade_version_in_astro_db {
  PRISMA=$(kubectl get pods -n $NAMESPACE | grep prisma | head -n1 | awk '{ print $1}')
  fail_with 'failed to find prisma pod'
  QUERY="UPDATE houston\$default.\"Deployment\" SET version = '${UPGRADE_TO_VERSION_AIRFLOW}';"
  PRISMA_DB_URI=`kubectl exec -n $NAMESPACE $PRISMA env | grep 'PRISMA_DB_URI=' | cut -c15-`
  echo "prisma pod: $PRISMA"
  kubectl exec -n $NAMESPACE $PRISMA -- apk add postgresql-client
  fail_with 'failed install postgresql client in prisma pod'
  kubectl exec -n $NAMESPACE $PRISMA -- psql -Atx "$PRISMA_DB_URI" -c "$QUERY"
  fail_with 'failed upgrade airflow version in astro DB'
}

function check_get_deployments_safe {
  echo "Confirming these Helm releases are indeed Astronomer Airflow deployments..."
  for release in $RELEASE_NAMES; do
    executor=$(helm get values $release --output json | jq '.executor' | grep -E 'CeleryExecutor|KubernetesExecutor|LocalExecutor')
    fail_with "Did not find an executor for $release, aborting because we expected this would be an Astronomer deployment"
    echo "    $release: $executor"
  done
  echo "We found an executor for all Helm release names, so we can be confident these are Astronomer Airflow deployments."
}

function get_deployments {
  echo "Looking for Astronomer Airflow helm releases..."
  export RELEASE_NAMES=$(helm list | grep airflow | grep $NAMESPACE | awk '{ print $1 }')
  fail_with "Did not find any Astronomer Airflow helm releases. What does 'helm list | grep airflow' show?"
  check_get_deployments_safe
}

function get_namespace_of_release {
  namespace_of_release_result=$(helm status $1 | grep -i namespace | head -n 1 | awk '{ print $2 }')
  fail_with "Failed to find the namespace of helm release $1. What does 'helm status $1' show?"
  kubectl get namespaces | grep "$namespace_of_release_result" > /dev/null
  fail_with "Failed to find the namespace of release $1: ERROR did not find a namespace $namespace_of_release_result in Kubernetes"
}

function check_cli_tools_installed {
  for executable in $@; do
    which $executable > /dev/null 2>&1
    fail_with "Please ensure $executable is installed in PATH"
    echo "$executable is in PATH"
  done
}

function check_helm_version_client {
  echo "Checking the version of Helm installed on the client (where this script is executed)..."
  helm version | grep Client | grep $1 > /dev/null
  if ! [[ $? -eq 0 ]]; then
    echo ""
    echo "==============="
    echo "Action required:"
    echo "Helm 2.17.0 is the version that this script was tested with."
    echo "Please install Helm 2.17.0."
    echo "Link: https://github.com/helm/helm/releases/tag/v2.17.0"
    exit 1
  else
    echo "Confirmed Helm 2.17.0 is installed."
  fi
}

# Sanity checks to confirm some assumptions
# about the environment
function kube_checks {
  echo "Checking kube authentication..."
  namespaces=$(kubectl get namespaces)
  fail_with "Failed to run 'kubectl get namespaces'. Please check kubectl configuration."
  echo "kubectl is installed and we can access a kube cluster."
  echo "$namespaces" | grep $NAMESPACE > /dev/null
  fail_with "Failed find the namespace $NAMESPACE"
  echo "Confirmed the presence of the namespace $NAMESPACE"
  echo "Checking that the release $RELEASE_NAME corresponds to the namespace $NAMESPACE"
  get_namespace_of_release $RELEASE_NAME
  if ! [[ "$namespace_of_release_result" = "$NAMESPACE" ]]; then
    echo "ERROR did not find the namespace of helm release $RELEASE_NAME to be $NAMESPACE, but instead found it to be $namespace_of_release_result"
    exit 1
  else
    echo "Confirmed! Found that Helm release $RELEASE_NAME is in namespace $NAMESPACE"
  fi
}

function get_helm_values_of_release {
  export values_result=$(helm get values --output json $1)
  fail_with "Did not find a Helm release $1"
}

function add_fernet_to_values {
  release_name=$1
  release_namespace=$2
  fernet_key=$3
  get_chart_version $release_name
  echo "    Begin fernet key persistence procedure for $release_name, airflow chart version $version_result"
  helm get values $release_name > $backup_dir/$release_name.yaml
  fail_with "Failed to get helm values of $release_name"
  echo "    Upgrading helm chart."
  helm upgrade -f $backup_dir/$release_name.yaml --set fernetKey="$fernet_key" --version "$version_result" --namespace $release_namespace $release_name astronomer/airflow
  fail_with "Failed to add fernet key to values of $release_name"
  echo "    Done."
}

function save_helm_values {
  # Find all the Astronomer Airflow deployments
  get_deployments
  echo "Backing up Airflow deployment helm values..."
  backup_dir=helm-values-backup
  mkdir $backup_dir
  fail_with "There is already a backup directory ./$backup_dir, but that is where we wanted to back up helm chart values. Please deal with this before proceeding."
  for release in $RELEASE_NAMES; do
    echo "Processing $release..."
    helm get $release > $backup_dir/$release-all-values.yaml
    fail_with "Failed to run 'helm get $release'"
    helm get values $release > $backup_dir/$release-user-values.yaml
    fail_with "Failed to run 'helm get values $release'"

    get_namespace_of_release $release
    echo "  Determined namespace is : $namespace_of_release_result"
    # Find the secret's actual value
    fernet=$(kubectl get secret -n $namespace_of_release_result \
      ${release}-fernet-key -o jsonpath="{.data.fernet-key}" | base64 --decode)
    fail_with "Failed to find secret $release-fernet-key"
    decoded_length=$(echo "$fernet" | base64 --decode | wc | awk '{ print $3 }')
    fail_with "Failed decode fernet key"
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
      echo "backing up the helm values again after adding the fernet key"
      mv $backup_dir/$release-all-values.yaml $backup_dir/$release-all-values.yaml.before-fernet
      mv $backup_dir/$release-user-values.yaml $backup_dir/$release-user-values.yaml.before-fernet
      helm get $release > $backup_dir/$release-all-values.yaml
      fail_with "Failed to run 'helm get $release'"
      helm get values $release > $backup_dir/$release-user-values.yaml
      fail_with "Failed to run 'helm get values $release'"
      echo "Checking that the fernet key was added successfully"
      get_helm_values_of_release $release
      configured_fernet=$(echo "$values_result" | jq '.fernetKey' --raw-output)
      if [[ "$configured_fernet" = "$fernet" ]]; then
        echo "  This fernet key is already configured in Helm"
      else
        echo "  We tried to add the fernet key to values, but when we checked if it was added, it was not there"
        exit 1
      fi
    fi

  done
  echo "Backing up Astronomer helm values..."
  release=$RELEASE_NAME
  helm get $release > $backup_dir/$release-all-values.yaml
  fail_with "Failed to run 'helm get $release'"
  helm get values $release > $backup_dir/$release-user-values.yaml
  fail_with "Failed to run 'helm get values $release'"
  echo $RELEASE_NAMES > $backup_dir/release_names.txt
}

function main {
  if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Please provide two arguments: helm release name (check with 'helm list'), and kubernetes namespace"
    exit 1
  fi
  export RELEASE_NAME=$1
  export NAMESPACE=$2

  # Pre-flight checks
  check_helm_version_client '2.17.0'
  check_cli_tools_installed helm kubectl jq head tail grep awk base64 cut wc
  kube_checks

  # Initialize helm
  helm init --client-only
  # Install astronomer and airflow chart
  helm repo add astronomer https://helm.astronomer.io
  helm repo update

  get_chart_version $RELEASE_NAME
  CURRENT_CHART_VERSION=$version_result

  export UPGRADE_TO_VERSION=$(helm search -l astronomer/astronomer | head -n2 | tail -n1 | awk '{ print $2 }')
  fail_with "Failed to search helm repositories for astronomer/astronomer"
  export UPGRADE_TO_VERSION_AIRFLOW=$(helm search -l astronomer/airflow | head -n2 | tail -n1 | awk '{ print $2 }')
  fail_with "Failed to search helm repositories for astronomer/airflow"
  echo ""
  echo ""
  read -p "Are you using single-namespace mode (where airflow and astronomer all in same namespace? (y/n)" CONT
  if [ "$CONT" = "y" ]; then
    echo "This script does not work with single namespace mode. Please contact Astronomer support"
    exit 1
  fi
  echo "Please create a backup of your database."
  read -p "Did you create a backup/snapshot of your database? (y/n)" CONT
  if ! [ "$CONT" = "y" ]; then
    exit 1
  fi
  echo "Upgrading Astronomer to version $UPGRADE_TO_VERSION, and Airflow helm charts to version $UPGRADE_TO_VERSION_AIRFLOW"
  read -p "Continue? (y/n)" CONT
  if ! [ "$CONT" = "y" ]; then
    exit 1
  fi

  save_helm_values

  RELEASE_NAMES=$(cat $backup_dir/release_names.txt)
  fail_with "Failed to find release names"

  echo "Updating Astronomer..."
  echo "Updating Astronomer... (1/3) Updating Astronomer platform, please allow up to 10 minutes"
  helm upgrade --namespace $NAMESPACE \
               -f $backup_dir/$RELEASE_NAME-user-values.yaml \
               --version $UPGRADE_TO_VERSION \
               --force \
               --timeout 600 \
               --set global.postgresqlEnabled=false \
               --set astronomer.houston.expireDeployments.enabled=false \
               --set astronomer.houston.cleanupDeployments.enabled=false \
               --set astronomer.houston.upgradeDeployments.enabled=false \
               --set astronomer.houston.config.deployments.chart.version=$UPGRADE_TO_VERSION_AIRFLOW \
               --set astronomer.houston.regenerateCaEachUpgrade=true \
              $RELEASE_NAME \
              astronomer/astronomer
  fail_with "Failed to upgrade Astronomer"
  echo "Updating Astronomer... (2/3) Reinstalling Airflow deployments"
  for release in $RELEASE_NAMES; do
    echo "Removing airflow release $release"
    helm delete --purge $release
    fail_with "Failed to purge $release"
    sleep 10
    echo "Installing airflow release $release"
    helm install --namespace $NAMESPACE-$release \
                 $release \
                 --set webserver.defaultUser.enabled=false \
                 --set webserver.jwtSigningCertificateSecretName=$RELEASE_NAME-houston-jwt-signing-certificate \
                 -f $backup_dir/$release-user-values.yaml \
                 --version $UPGRADE_TO_VERSION_AIRFLOW \
                 astronomer/airflow
    fail_with "Failed to install $release"
  done
  # Since the upgrade was not performed by houston, inform houston by
  # upgrading the 'version' field in the database
  echo "Updating Astronomer... (3/3) Syncing Airflow deployments version in Astro DB"
  upgrade_version_in_astro_db

  echo "Done! Please contact Astronomer support if any issues are detected."
  echo ""
  echo "Please install the new CLI:"
  echo "curl -sSL https://install.astronomer.io | sudo bash -s -- v0.12.0"
  echo ""
  echo "Please Upgrade your Airflow version by changing your Dockerfile:"
  echo "FROM quay.io/astronomer/ap-airflow:1.10.7-alpine3.10-onbuild"
}

main $1 $2
