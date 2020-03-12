# Kind Development

This directory contains scripts for assisting
with creating a GCP VM and installing
Astronomer Platform in Kind.

The purpose is to enable development of the
CI pipeline outside of CI.

VM Lifecycle

```shell
# Create a VM and run startup-script
./bin/kind/boot-dev-vm.sh

# Log into VM
gcloud compute ssh kind-dev-$(USER)

# Cleanup VM
gcloud compute ssh kind-dev-$(USER)
```

Simulating CircleCI (assumes you are logged into the VM)

```shell
# Get the code on the VM (you can use scp too)
git clone https://github.com/astronomer/astronomer
cd astronomer

# Prep and start Kind
./bin/install-ci-tools
./bin/setup-kind

# Astronomer Install
./bin/install-platform
./bin/waitfor-platform

# Run Platform Tests
helm test astronomer
```
