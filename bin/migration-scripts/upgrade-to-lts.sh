#!/bin/bash

: "${TILLER_NAMESPACE:=kube-system}"

backup_dir=helm-values-backup

function fail_with {
  # shellcheck disable=SC2181
  if [ $? -ne 0 ]; then
    echo "$1"
    exit 1
  fi
}

function determine_helm_version {
  echo "Determining which version of Helm is being used for Astronomer"
  HELM_VERSION="2"
  if ! helm status "$RELEASE_NAME" > /dev/null 2>&1 ; then
    HELM_VERSION="3"
    helm3 status -n "$NAMESPACE" "$RELEASE_NAME" > /dev/null 2>&1
    fail_with "Failed to determine Helm version being used for Astronomer"
  else
    if helm3 status -n "$NAMESPACE" "$RELEASE_NAME" > /dev/null 2>&1 ; then
      echo "ERROR: found Astronomer to be installed in both Helm 2 and Helm 3"
      exit 1
    fi
  fi
  echo "Determined Astronomer is running Helm version $HELM_VERSION"
}

function get_chart_version {
  version_result=$(helm list "^${1}$" | grep "^${1}\b" | awk '{ print $(9) }' | awk -F'-' '{ print $NF }')
}

# this is a temporary workaround
function upgrade_version_in_astro_db {
  PRISMA=$(kubectl get pods -n "$NAMESPACE" | grep prisma | head -n1 | awk '{ print $1}')
  fail_with 'failed to find prisma pod'
  QUERY="UPDATE houston\$default.\"Deployment\" SET version = '${UPGRADE_TO_VERSION_AIRFLOW}';"
  PRISMA_DB_URI=$(kubectl exec -n "$NAMESPACE" "$PRISMA" env | grep 'PRISMA_DB_URI=' | cut -c15-)
  echo "prisma pod: $PRISMA"
  kubectl exec -n "$NAMESPACE" "$PRISMA" -- apk add postgresql-client
  fail_with 'failed install postgresql client in prisma pod'
  if ! kubectl exec -n "$NAMESPACE" "$PRISMA" -- psql -Atx "$PRISMA_DB_URI" -c "$QUERY" ; then
    echo "Failed to update Airflow chart version in DB. Retrying in 60 seconds..."
    sleep 60
    PRISMA=$(kubectl get pods -n "$NAMESPACE" | grep prisma | head -n1 | awk '{ print $1}')
    PRISMA_DB_URI=$(kubectl exec -n "$NAMESPACE" "$PRISMA" env | grep 'PRISMA_DB_URI=' | cut -c15-)
    kubectl exec -n "$NAMESPACE" "$PRISMA" -- apk add postgresql-client
    fail_with 'failed install postgresql client in prisma pod'
    kubectl exec -n "$NAMESPACE" "$PRISMA" -- psql -Atx "$PRISMA_DB_URI" -c "$QUERY"
    fail_with 'failed upgrade airflow version in astro DB'
  fi
}

function check_get_deployments_safe {
  echo "Confirming these Helm releases are indeed Astronomer Airflow deployments..."
  for release in $RELEASE_NAMES; do
    executor=$(helm get values "$release" --output json | jq '.executor' | grep -E 'CeleryExecutor|KubernetesExecutor|LocalExecutor')
    fail_with "Did not find an executor for $release, aborting because we expected this would be an Astronomer deployment"
    echo "    $release: $executor"
  done
  for release in $RELEASE_NAMES_HELM3; do
    executor=$(helm3 get values -n "$NAMESPACE-$release" "$release" --output json | jq '.executor' | grep -E 'CeleryExecutor|KubernetesExecutor|LocalExecutor')
    fail_with "Did not find an executor for $release, aborting because we expected this would be an Astronomer deployment"
    echo "    $release: $executor"
  done
  echo "We found an executor for all Helm release names, so we can be confident these are Astronomer Airflow deployments."
}

function get_deployments {
  echo "Looking for Astronomer Airflow helm releases..."
  RELEASE_NAMES=$(helm list --max 1000 | grep airflow | grep "$NAMESPACE" | awk '{ print $1 }')
  export RELEASE_NAMES
  RELEASE_NAMES_HELM3=$(helm3 list --all-namespaces --max 1000 | grep airflow | grep "$NAMESPACE" | awk '{ print $1 }')
  fail_with "Did not find any Astronomer Airflow helm releases. What does 'helm list | grep airflow' show?"
  export RELEASE_NAMES_HELM3
  check_get_deployments_safe
}

function get_namespace_of_release {
  if ! [ "$HELM_VERSION" -eq "2" ]; then
    echo "ERROR: get_namespace_of_release should only be called in helm 2 mode"
  fi
  namespace_of_release_result=$(helm status "$1" | grep -i namespace | head -n 1 | awk '{ print $2 }')
  fail_with "Failed to find the namespace of helm release $1. What does 'helm status $1' show?"
  kubectl get namespaces | grep "$namespace_of_release_result" > /dev/null
  fail_with "Failed to find the namespace of release $1: ERROR did not find a namespace $namespace_of_release_result in Kubernetes"
}

function check_cli_tools_installed {
  for executable in "$@" ; do
    command -v "$executable" > /dev/null 2>&1
    fail_with "Please ensure $executable is installed in PATH"
    echo "$executable is in PATH"
  done
}

function check_helm3_version_client {
  echo "Checking that Helm $1 is installed on the client (where this script is executed)..."
  if ! helm3 version | grep "$1" > /dev/null ; then
    echo
    echo "==============="
    echo "Action required:"
    echo "Helm $1 is the version that this script was tested with."
    echo "Please install Helm $1 in your PATH as 'helm3'"
    echo "Link: https://github.com/helm/helm/releases/tag/v$1"
    exit 1
  else
    echo "Confirmed Helm $1 is installed."
  fi
}

function check_helm_version_client {
  echo "Checking that Helm $1 is installed on the client (where this script is executed)..."
  if ! helm version | grep Client | grep "$1" > /dev/null ; then
    echo
    echo "==============="
    echo "Action required:"
    echo "Helm $1 is the version that this script was tested with."
    echo "Please install Helm $1."
    echo "Link: https://github.com/helm/helm/releases/tag/v$1"
    exit 1
  else
    echo "Confirmed Helm $1 is installed."
  fi
}

# Sanity checks to confirm some assumptions
# about the environment
function kube_checks {
  echo "Checking kube authentication..."
  kubectl get namespace > /dev/null
  fail_with "Failed to run 'kubectl get namespaces'. Please check kubectl configuration."
  echo "kubectl is installed and we can access a kube cluster."
  kubectl get namespace "$NAMESPACE" > /dev/null
  fail_with "Failed find the namespace $NAMESPACE"
  echo "Confirmed the presence of the namespace $NAMESPACE"
  echo "Checking that the release $RELEASE_NAME corresponds to the namespace $NAMESPACE"
  if [ "$HELM_VERSION" -eq "2" ]; then
    echo "Using Helm 2 to get the namespace of release $RELEASE_NAME"
    get_namespace_of_release "$RELEASE_NAME"
    if ! [[ "$namespace_of_release_result" = "$NAMESPACE" ]]; then
      echo "ERROR did not find the namespace of helm release $RELEASE_NAME to be $NAMESPACE, but instead found it to be $namespace_of_release_result"
      exit 1
    else
      echo "Confirmed! Found that Helm 2 release $RELEASE_NAME is in namespace $NAMESPACE"
    fi
  elif [ "$HELM_VERSION" -eq "3" ]; then
    echo "Using Helm 3 to confirm that release name $RELEASE_NAME is in namespace $NAMESPACE"
    helm3 status -n "$NAMESPACE" "$RELEASE_NAME" > /dev/null
    fail_with "ERROR did not find the namespace of helm release $RELEASE_NAME to be $NAMESPACE"
  else
    echo "ERROR: HELM_VERSION is supposed to be 2 or 3, but it's '$HELM_VERSION'"
    exit 1
  fi
}

function get_helm_values_of_release {
  values_result=$(helm get values --output json "$1")
  fail_with "Did not find a Helm release $1"
  export values_result
}

function add_fernet_to_values {
  release_name=$1
  release_namespace=$2
  fernet_key=$3
  get_chart_version "$release_name"
  echo "    Begin fernet key persistence procedure for $release_name, airflow chart version $version_result"
  helm get values "$release_name" > "$backup_dir/$release_name.yaml"
  fail_with "Failed to get helm values of $release_name"
  echo "    Upgrading helm chart."
  helm upgrade -f "$backup_dir/$release_name.yaml" --set fernetKey="$fernet_key" --version "$version_result" --namespace "$release_namespace" "$release_name" astronomer/airflow
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
  echo "Backing up Helm 2 Airflow values"
  for release in $RELEASE_NAMES; do
    echo "Processing $release..."
    helm get "$release" > "$backup_dir/$release-all-values.yaml"
    fail_with "Failed to run 'helm get $release'"
    helm get values "$release" > "$backup_dir/$release-user-values.yaml"
    fail_with "Failed to run 'helm get values $release'"

    fernet=$(kubectl get secret -n "$NAMESPACE-$release" \
      "${release}-fernet-key" -o jsonpath="{.data.fernet-key}" | base64 --decode)
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
    get_helm_values_of_release "$release"
    configured_fernet=$(echo "$values_result" | jq '.fernetKey' --raw-output)
    if [[ "$configured_fernet" == "$fernet" ]]; then
      echo "  This fernet key is already configured in Helm"
    else
      echo "  Detected that the fernet key needs to be added to the Helm values."
      add_fernet_to_values "$release" "$namespace_of_release_result" "$fernet"
      echo "backing up the helm values again after adding the fernet key"
      mv "$backup_dir/$release-all-values.yaml" "$backup_dir/$release-all-values.yaml.before-fernet"
      mv "$backup_dir/$release-user-values.yaml" "$backup_dir/$release-user-values.yaml.before-fernet"
      helm get "$release" > "$backup_dir/$release-all-values.yaml"
      fail_with "Failed to run 'helm get $release'"
      helm get values "$release" > "$backup_dir/$release-user-values.yaml"
      fail_with "Failed to run 'helm get values $release'"
      echo "Checking that the fernet key was added successfully"
      get_helm_values_of_release "$release"
      configured_fernet=$(echo "$values_result" | jq '.fernetKey' --raw-output)
      if [[ "$configured_fernet" = "$fernet" ]]; then
        echo "  This fernet key is already configured in Helm"
      else
        echo "  We tried to add the fernet key to values, but when we checked if it was added, it was not there"
        exit 1
      fi
    fi

  done
  echo "Backing up Helm 3 Airflow values"
  for release in $RELEASE_NAMES_HELM3; do
    echo "Processing $release..."
    if [ -f "$backup_dir/$release-all-values.yaml" ] || [ -f "$backup_dir/$release-user-values.yaml" ]; then
      echo "ERROR: there is both a helm 2 and helm 3 release for $release, this is not expected."
      exit 1
    fi
    helm3 get values --all -n "$NAMESPACE-$release" "$release" > "$backup_dir/$release-all-values.yaml"
    fail_with "Failed to run 'helm3 get values --all -n $NAMESPACE-$release $release'"
    helm3 get values -n "$NAMESPACE-$release" "$release" > "$backup_dir/$release-user-values.yaml"
    fail_with "Failed to run 'helm3 get values -n $NAMESPACE-$release $release'"
  done
  echo "Backing up Astronomer helm values..."
  release=$RELEASE_NAME
  if [ "$HELM_VERSION" -eq "2" ]; then
    helm get "$release" > "$backup_dir/$release-all-values.yaml"
    fail_with "Failed to run 'helm get $release'"
    helm get values "$release" > "$backup_dir/$release-user-values.yaml"
    fail_with "Failed to run 'helm get values $release'"
  elif [ "$HELM_VERSION" -eq "3" ]; then
    helm3 get values --all -n "$NAMESPACE" "$release" > "$backup_dir/$release-all-values.yaml"
    fail_with "Failed to run 'helm get $release'"
    helm3 get values -n "$NAMESPACE" "$release" > "$backup_dir/$release-user-values.yaml"
    fail_with "Failed to run 'helm get values $release'"
  else
    echo "ERROR: HELM_VERSION is supposed to be 2 or 3, but it's '$HELM_VERSION'"
    exit 1
  fi
  echo "$RELEASE_NAMES" > "$backup_dir/release_names.txt"
  echo "$RELEASE_NAMES_HELM3" > "$backup_dir/release_names_helm3.txt"
}

function helm2_to_3 {
  HELM2_RELEASES=()
  while IFS='' read -r line ; do
    HELM2_RELEASES+=("$line")
  done < <(kubectl get secret,configmap -n "$TILLER_NAMESPACE" -l "OWNER=TILLER" -o name |
    grep -v 'No resources' |
    cut -d '.' -f1 |
    cut -d '/' -f2 |
    uniq)
  [ "${#HELM2_RELEASES}" -gt 0 ]
  fail_with "Failed to find helm 2 releases"
  RELEASES_TO_UPGRADE=()
  set +e
  for release in "${HELM2_RELEASES[@]}" ; do
    if helm list "^${release}$" | tail -n 1 | grep -E "astronomer|airflow" > /dev/null ; then
      RELEASES_TO_UPGRADE+=( "$release" )
    fi
  done
  if [ "${#RELEASES_TO_UPGRADE[@]}" -gt 0 ]; then
    echo "Non zero Airflow and Astronomer releases on Helm 2. Performing Helm 2 to Helm 3 upgrade procedure"
    echo "Scaling down ingress so nobody can access Astronomer, this avoids race conditions of the upgrade process against customer activity"
    kubectl scale --replicas=0 -n "$NAMESPACE" "deployment/${RELEASE_NAME}-nginx"
    echo "Scaling down commander, this ensures that old commander can't be used during the upgrade procedure"
    kubectl scale --replicas=0 -n "$NAMESPACE" "deployment/${RELEASE_NAME}-commander"
    echo "Upgrading releases"
    # Upgrade the releases
    for release in "${RELEASES_TO_UPGRADE[@]}" ; do
      helm3 2to3 convert --tiller-ns "$TILLER_NAMESPACE" --delete-v2-releases "$release"
      fail_with "Failed to convert $release from helm 2 to helm 3, please read the above helm log"
    done
  fi
}

function interactive_confirmation {
  echo
  echo
  echo "Is tiller in the namespace $TILLER_NAMESPACE ?"
  read -r -p "(y/n) " CONT
  if ! [ "$CONT" = "y" ]; then
    echo "Please modify the TILLER_NAMESPACE environment variable"
    exit 1
  fi
  read -r -p "Are you using single-namespace mode (where airflow and astronomer all in same namespace? (y/n) " CONT
  if [ "$CONT" = "y" ]; then
    echo "This script does not work with single namespace mode. Please contact Astronomer support"
    exit 1
  fi
  echo "Please create a backup of your database."
  read -r -p "Did you create a backup/snapshot of your database? (y/n) " CONT
  if ! [ "$CONT" = "y" ]; then
    exit 1
  fi
  echo "Upgrading Astronomer to version $UPGRADE_TO_VERSION from version $CURRENT_CHART_VERSION, and Airflow helm charts to version $UPGRADE_TO_VERSION_AIRFLOW"
  read -r -p "Continue? (y/n) " CONT
  if ! [ "$CONT" = "y" ]; then
    exit 1
  fi
}

function setup_helm {
  # Initialize helm
  helm init --client-only
  helm3 plugin install https://github.com/helm/helm-2to3.git
  # Install astronomer and airflow chart
  helm repo add astronomer https://helm.astronomer.io
  helm3 repo add astronomer https://helm.astronomer.io
  helm repo update
  helm3 repo update
}

function collect_current_version_info {
  if [ "$HELM_VERSION" -eq "2" ]; then
    version_result=$(helm list "^${RELEASE_NAME}$" | grep "$RELEASE_NAME" | awk '{ print $9 }' | awk -F'-' '{ print $NF }')
    fail_with "Failed to find chart version"
  elif [ "$HELM_VERSION" -eq "3" ]; then
    version_result=$(helm3 list --all-namespaces --filter "$RELEASE_NAME" | grep "$RELEASE_NAME" | awk '{ print $9 }' | awk -F'-' '{ print $NF }')
    fail_with "Failed to find chart version"
  else
    echo "ERROR: HELM_VERSION is supposed to be 2 or 3, but it's '$HELM_VERSION'"
    exit 1
  fi
  CURRENT_CHART_VERSION=$version_result
  CURRENT_MINOR_VERSION=$(echo "$CURRENT_CHART_VERSION" | cut -d'.' -f2)
  SHOULD_USE_GIT_CLONE=0
  if [[ "$CURRENT_MINOR_VERSION" -lt 12 ]]; then
    SHOULD_USE_GIT_CLONE=1
    echo "In this version of astronomer, we want to install from git repository"
  else
    echo "In this version of astronomer, we want to install from helm repository"
  fi
  echo "Found current chart full version to be $version_result"
  echo "Found current chart minor version to be $CURRENT_MINOR_VERSION"
}

function git_clone_if_necessary {
  # condition if CURRENT_CHART_VERSION is less than 0.12, do clone
  CHART="astronomer/astronomer"
  set -e
  if [[ "$SHOULD_USE_GIT_CLONE" -eq "1" ]]; then
    CHART="./astronomer-${CURRENT_CHART_VERSION}"
    git clone https://github.com/astronomer/helm.astronomer.io.git astronomer
    cd astronomer
    git checkout "v$CURRENT_CHART_VERSION"
    cd ..
    mv astronomer "astronomer-$CURRENT_CHART_VERSION"
  fi
  set +e
}

function main {
  if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Please provide two arguments: helm release name (check with 'helm list'), and kubernetes namespace"
    exit 1
  fi
  export RELEASE_NAME=$1
  export NAMESPACE=$2
  export UPGRADE_TO_VERSION_AIRFLOW=0.15.2

  # Pre-flight checks
  check_helm_version_client '2.16.12'
  check_helm3_version_client '3.3.4'
  check_cli_tools_installed helm kubectl jq head tail grep awk base64 cut wc git

  determine_helm_version

  kube_checks

  setup_helm

  UPGRADE_TO_VERSION=$(helm3 search repo astronomer/astronomer --version 0.16 | head -n2 | tail -n1 | awk '{ print $2 }')
  export UPGRADE_TO_VERSION

  collect_current_version_info

  interactive_confirmation

  save_helm_values

  helm2_to_3

  git_clone_if_necessary

  kubectl delete sts --cascade=false --namespace "$NAMESPACE" "${RELEASE_NAME}-elasticsearch-master" "${RELEASE_NAME}-elasticsearch-data" || true
  sleep 5
  echo "Upgrading Astronomer... (1/4) converge Helm 3 labels"
  helm3 upgrade --namespace "$NAMESPACE" \
               --reset-values \
               -f "$backup_dir/$RELEASE_NAME-user-values.yaml" \
               --version "$CURRENT_CHART_VERSION" \
               --timeout 1200s \
               --set global.postgresqlEnabled=false \
               --set astronomer.houston.expireDeployments.enabled=false \
               --set astronomer.houston.cleanupDeployments.enabled=false \
               --set astronomer.houston.upgradeDeployments.enabled=false \
               --set astronomer.airflowChartVersion="$UPGRADE_TO_VERSION_AIRFLOW" \
               --set astronomer.houston.regenerateCaEachUpgrade=true \
              "$RELEASE_NAME" \
              "$CHART"
  fail_with "Failed to upgrade Astronomer"
  sleep 5
  echo "Upgrading Astronomer... (2/4) upgrade Astronomer"
  helm3 upgrade --namespace "$NAMESPACE" \
               -f "$backup_dir/$RELEASE_NAME-user-values.yaml" \
               --version "$UPGRADE_TO_VERSION" \
               --timeout 1200s \
               --set global.postgresqlEnabled=false \
               --set astronomer.houston.expireDeployments.enabled=false \
               --set astronomer.houston.cleanupDeployments.enabled=false \
               --set astronomer.houston.upgradeDeployments.enabled=false \
               --set astronomer.airflowChartVersion="$UPGRADE_TO_VERSION_AIRFLOW" \
               --set astronomer.houston.config.deployments.chart.version="$UPGRADE_TO_VERSION_AIRFLOW" \
               --set astronomer.houston.regenerateCaEachUpgrade=true \
              "$RELEASE_NAME" \
              astronomer/astronomer
  fail_with "Failed to upgrade Astronomer"

  # give prisma time to get ready
  sleep 120
  # Since the upgrade was not performed by houston, inform houston by
  # upgrading the 'version' field in the database
  echo "Updating Astronomer... (3/4) Upgrading Airflow deployments version"
  upgrade_version_in_astro_db

  echo "Reinstall all Airflow releases with new airflow chart version"
  for release in $RELEASE_NAMES $RELEASE_NAMES_HELM3; do
    echo "Removing Airflow release $release"
    helm3 delete --namespace "$NAMESPACE-$release" "$release"
    fail_with "Failed to purge $release"
    sleep 5
    echo "Installing airflow release $release"
    helm3 install --namespace "$NAMESPACE-$release" \
                 "$release" \
                 --set webserver.defaultUser.enabled=false \
                 --set webserver.jwtSigningCertificateSecretName="$RELEASE_NAME-houston-jwt-signing-certificate" \
                 -f "$backup_dir/$release-user-values.yaml" \
                 --version $UPGRADE_TO_VERSION_AIRFLOW \
                 astronomer/airflow
    fail_with "Failed to install $release"
  done

  echo "Upgrading Astronomer... (4/4) Ensure Helm upgrade works to reconfigure platform"
  helm3 upgrade --namespace "$NAMESPACE" \
                -f "$backup_dir/$RELEASE_NAME-user-values.yaml" \
                --version "$UPGRADE_TO_VERSION" \
                --timeout 1200s \
                --set global.postgresqlEnabled=false \
                --set astronomer.houston.expireDeployments.enabled=false \
                --set astronomer.houston.cleanupDeployments.enabled=false \
                --set astronomer.houston.upgradeDeployments.enabled=true \
                --set astronomer.airflowChartVersion="$UPGRADE_TO_VERSION_AIRFLOW" \
                --set astronomer.houston.config.deployments.chart.version="$UPGRADE_TO_VERSION_AIRFLOW" \
                --set astronomer.houston.regenerateCaEachUpgrade=false \
                "$RELEASE_NAME" \
                astronomer/astronomer
  fail_with "Failed to upgrade Astronomer"


  echo "Done! Please contact Astronomer support if any issues are detected."
  echo
  echo "Please install the new CLI:"
  echo "curl -sSL https://install.astronomer.io | sudo bash -s -- v0.16.1"
  echo
  echo "You may choose to upgrade Airflow versions by changing your Dockerfile, for example:"
  echo "FROM quay.io/astronomer/ap-airflow:1.10.10-alpine3.10-onbuild"
}

main "$1" "$2"
