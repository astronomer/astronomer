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
gcloud compute instances delete --quiet kind-dev-$(USER) --zone us-east4-a
```

Simulating CircleCI (assumes you are logged into the VM)

```shell
# Get the code on the VM (you can use scp too)
git clone https://github.com/astronomer/astronomer
cd astronomer

# (OPTIONAL) git checkout a branch for chart development

# Prep and start Kind
./bin/kind/install-docker.sh
./bin/install-ci-tools
echo "PATH=$PATH:/tmp/bin" >> $HOME/.profile
exit

# Log back in to get updated user profile
gcloud compute ssh kind-dev-$(USER)
cd astronomer

# (OPTIONAL) Set Kubernetes Version
# Look in .circleci/config.yml for the latest CI versions
#   or set to any version supported by Kind
#   this value is exported by CircleCI
#   the default otherwise is in bin/setup-kind
export KUBE_VERSION="v1.18.15"

# Astronomer Install
./bin/setup-kind
./bin/install-platform
./bin/waitfor-platform

# Expose platform Nginx, run in background
echo "172.17.0.1 local.astronomer-development.com" | sudo tee -a /etc/hosts
sudo /tmp/bin/kubectl port-forward -n astronomer svc/astronomer-nginx 80 443 &
<enter> # To see prompt again, output will be interlaced

# Create Initial User
./bin/create-initial-user "<username>" "<password>"

# Stop background port-forward
fg
<CTRL>-C

# Run Platform Tests
helm test astronomer

# Debug: Check Logs
kubectl -n astronomer describe po/astronomer-ap-e2e-test
kubectl -n astronomer logs astronomer-ap-e2e-test

# Debug: Run Manually
kubectl apply -n astronomer -f bin/e2e-test/e2e-pod.yaml
kubectl exec -it -n astronomer manual-ap-e2e-test bash

# Cleanup VM
gcloud compute instances delete --quiet kind-dev-$(USER) --zone us-east4-a
```
