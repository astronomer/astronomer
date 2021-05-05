# Astronomer upgrade guide

If you are already on an LTS version and you are seeking a patch version update or to just reconfigure the software, please skip to the bottom section "patch version updates"

## Astronomer versioning: moving to the long-term-support (LTS) software versioning model

We have customers running Astronomer versions 0.7 through 0.16, and we currently support all of them. The wide variety of configurations and versions present in our customer's environments and the accelerating new minor version release cycle has presented challenges with regard to training support engineering, backporting fixes, documenting change notes, and with upgrades. In July 2020, Astronomer decided to start following the long-term-support (LTS) model for enterprise-ready Astronomer versions. This will look like some of our minor versions receive continuous patching while the others do not. This allows our developers to focus on building new features and limiting the number of versions where they need to backport patches. In the near future, we will be only publicly publishing the LTS versions. The release cadence is not yet decided but it will be somewhere in between 1 month and 6 months, depending on how many LTS versions we plan to support at the same time.

Astronomer will provide a script to automatically upgrade customers from any version 0.7 or later to the first LTS version 0.16 (included in this directory - read on). Then, moving forward, Astronomer will provide automatic upgrades between each new LTS version.

## Advanced cases that require Astronomer support

If you are in one of these categories, please contact Astronomer support to help with your upgrade.

- More than 25 Helm releases
- Cluster shared with other Helm releases that are not Astronomer-related
- You are using the in-cluster DB option in the helm chart

## Schedule a change window with your Airflow users

- The upgrade procedure assumes that users are not modifying their Airflow deployments during the upgrade
- This procedure is expected to interrupt task execution for a few minutes on each deployment
- DAGs do not need to be paused if task failure and retry is configured in the DAG and acceptable to the user
- Scheduling 4 hours is recommended in order for Astronomer support to be able to resolve any potential issues in time. Please plan with Astronomer for support availability. If it works without a snag, it actually takes about 5-30 minutes, depending on how many Airflow deployments you are running.

## Local environment preparation

Install some command line tools:

- kubectl (version appropriate for your cluster's version or newer)
- [helm (version 2.16.12)](https://github.com/helm/helm/releases/tag/v2.16.12), please install into PATH as "helm"
- [helm 3 (version 3.3.4)](https://github.com/helm/helm/releases/tag/v3.3.4), please install into PATH as "helm3"
- [jq](https://stedolan.github.io/jq/download/)

On Mac, if you have brew, you can install 'jq' with:

```sh
brew install jq
```

## Kubernetes preparation

Ensure you are running on an Astronomer-supported version of Kubernetes. Currently, versions 1.16 through 1.18 are supported.

To perform the Kubernetes upgrade, please contact your cloud provider's support team.

## Collect installation-specific information

- Namespace in which the Astronomer platform is installed (example: 'astronomer')
- Helm release name of the Astronomer platform (example: 'astronomer')
- You can confirm the namespace with

```sh
kubectl get pods -n <namespace here>
```

- In the above output, you should see the Astronomer platform's Pods, such as a pod with name including 'houston' and also elasticsearch pods
- You can confirm the release name with

```sh
# helm 2
helm list <release name>
```

Or

```sh
# helm 3
helm3 list <release name> -n <namespace>
```

- Above, you should have found "astronomer" or "astronomer-platform" somewhere in the result line

## Upgrade script

- You will want to perform this step while users are not changing anything such as new deployments or deployment configuration changes

**If you are not on an LTS version yet, then you will upgrade to the first LTS version, 0.16**

- Download the 'upgrade-to-lts.sh' script and execute it with two arguments: release name, and namespace (see above 'collect installation-specific information')
- This script will write some .yaml files to your local directory inside of a directory 'helm-values-backup'. These are important to back up, and in combination with the DB backup can be used to restore deployments in the event that something goes wrong. These files include secrets.
- The script is interactive, so pay attention for a few questions
- If there is a failure, copy the output and report to Astronomer support
- There is one error message that might show up that can be ignored, this is a network hiccup error reported by Helm that automatically resolves itself:

```
E0401 22:10:07.041224   11330 portforward.go:372] error copying from remote stream to local connection: readfrom tcp4 127.0.0.1:45835->127.0.0.1:36720: write tcp4 127.0.0.1:45835->127.0.0.1:36720: write: broken pipe
```

**If you are on an LTS version**

- There will be a script to upgrade from each LTS version to the next, at the time of writing the first LTS version, 0.16 is the current most-recent version.

## Check that it worked

Here are a few things we can do to make sure everything worked as expected:

### 1) Check pods are ready

- Watch the pods stabilize, there should be zero crashlooping pods, and all should show 'Running' with full readiness "N/N" (not N-1 / N) or 'Completed' with 0/1 readiness

```sh
watch kubectl get pods -n <release namespace>
```

- If you find a pod crashlooping or some other kind of error right after the upgrade, first try deleting it (any pod in Astronomer is safe to delete)

```sh
kubectl delete pod -n <namespace> <pod name>
```

- Above: Astronomer has found a few pods (prometheus) sometimes need a delete after upgrading from an older version directly to 0.16
- If a pod is stuck "Terminating" (occasionally seen in old versions of Elasticsearch), then forcefully delete it

```sh
kubectl delete pod -n <namespace> <pod name> --grace-period 0 --force
```

- Check all the pods in your airflow namespaces

```sh
kubectl get pods --all-namespaces
```

- If you have crashlooping pods in the Airflow namespaces, contact Astronomer support.

### 2) Check on Astronomer features

- Check logs present for an old task less old than 15 days
- Check that metrics show up in the UI on the metrics tab
- Check that you can access the Airflow UI

### 3) Check that Airflow upgrades will work

- Find the houston pods

```sh
kubectl get pods -n astronomer | grep houston
```

- An example output is:

```
astronomer-houston-84945966d8-jc54j                       1/1     Running     0          3d
astronomer-houston-cleanup-deployments-1580083200-p8dk5   0/1     Completed   0          21h
astronomer-houston-expire-deployments-1580083200-jxsxj    0/1     Completed   0          21h
astronomer-houston-upgrade-deployments-lw9kc              0/1     Completed   0          3d21h
```

- Note: you may not have all these 0/1 pods above, depending on your configuration.
- Ensure that the Airflow chart upgrades are working my looking for errors in the pod that includes "upgrade-deployments"

```sh
# Use the pod name corresponding to your result of finding the houston pods
kubectl logs -n <release namespace> astronomer-houston-upgrade-deployments-lw9kc
```

- Check the airflow chart version, it should be the same and 0.15 for all airflow Helm releases

```sh
helm3 list --all-namespaces | grep -i airflow
```

- In the UI, check that you can deploy changes to Airflow by adding a new environment variable and deploying the change with the UI button while watching the pods in the corresponding namespace. You should see the Airflow components restart to get the new environment variable.

```sh
kubectl get pods -n <airflow namespace you are changing> -w
# then click the button in UI
```

- Now, again check your Airflow releases to make sure the Airflow chart version did not change - it should be the same result as before.

```sh
helm3 list --all-namespaces | grep -i airflow
```

## Patch version updates

If you are already on an LTS version, then you can update yourself much more simply. You can use normal helm3 commands to update your configuration or patch version, a sample script is provided below.

- First, ensure you have a copy of your Astronomer configuration if you don't already have one

```sh
helm3 get values -n <namespace> <release name of astronomer> > config.yaml
```

- review this configuration, and you can delete the line "USER-SUPPLIED VALUES:"
- check your current version

```sh
helm3 list --all-namespaces | grep astronomer
```

- Use a script like this to update Astronomer patch versions or reconfigurations, please review this script to understand what it is doing and substitute the variables with your own values

```sh
#!/bin/bash
set -xe

RELEASE_NAME=replace-this
NAMESPACE=replace-this
ASTRO_VERSION=0.16.replace-patch-version

helm3 repo add astronomer https://helm.astronomer.io
helm3 repo update

# upgradeDeployments false ensures that Airflow charts are not upgraded when this script is ran
# If you deployed a config change that is intended to reconfigure something inside Airflow,
# then you may set this value to "true" instead. When it is "true", then each Airflow chart will
# restart.
helm3 upgrade --namespace $NAMESPACE \
            -f ./config.yaml \
            --version $ASTRO_VERSION \
            --set astronomer.houston.upgradeDeployments.enabled=false \
            $RELEASE_NAME \
            astronomer/astronomer
```

# Common problems

Usually to solve an issue, it involves understanding what went wrong and manually resolving just that part, then re-running the script. The script is safe to re-run, just copy the helm-values-backup directory to somewhere else first, otherwise the script will fail indicating that it won't overwrite the backups.

## Helm migration

Helm 2to3 plugin is the least reliable part of this. I have found that it fails to migrate sometimes. In the event that the script fails due to helm 2to3 migration, then you can manually migrate releases like this:

If the release exists in helm 2 but not helm 3:

```sh
helm 2to3 convert --delete-v2-releases $release
```

If the release exists in helm 2 and helm 3:

```sh
helm 2to3 cleanup --name $release
```

If all else fails, delete and re-install this airflow to the new airflow chart version using the helm 3 and the helm chart values backup.

## Customer-specific resource collision

For example, maybe a customer created ingress object prometheus.basedomain before the platform added that in by default. In this case, the helm upgrade will fail. Just delete this resource and re-run the script.
