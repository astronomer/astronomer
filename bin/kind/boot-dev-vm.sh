#!/usr/bin/env bash
set -eou pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Basic config
ZONE="us-east4-a"
MACHINE_TYPE="n1-standard-8"
DISK_TYPE="pd-standard"
DISK_SIZE="250GB"
IMAGE_FAMILY="ubuntu-1604-lts"
IMAGE_PROJECT="ubuntu-os-cloud"

# This is actually port 22 in astronomer-cloud-dev
NETWORK_TAGS="http-server"

# just the file name, not contents
STARTUP=$DIR/startup-script.sh
METADATA="--metadata-from-file=startup-script=$STARTUP"

VM_NAME=${1:-kind-dev-$USER}

gcloud compute instances create $VM_NAME \
  --zone $ZONE \
  --machine-type $MACHINE_TYPE \
  --boot-disk-type=$DISK_TYPE \
  --boot-disk-size=$DISK_SIZE \
  --image-project ${IMAGE_PROJECT} \
  --image-family  ${IMAGE_FAMILY} \
  --tags $NETWORK_TAGS \
  $METADATA

