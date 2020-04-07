# Astronomer upgrade guide


## Schedule a change window

- The upgrade procedure assumes that users are not modifying their Airflow deployments during the upgrade
- This procedure is expected to interrupt task execution for a few minutes on each deployment
- Scheduling 4 hours is recommended in order for Astronomer support to be able to resolve any potential issues in time. Please plan with Astronomer for support availability. If it works without a snag, it actually takes about 5-30 minutes, depending on how many Airflow deployments you are running.

## Local environment preparation

Install some command line tools:

- kubectl (version appropriate for your cluster's version or newer)
- [helm (version 2.16.1)](https://github.com/helm/helm/releases/tag/v2.16.1)
- [jq](https://stedolan.github.io/jq/download/)

On Mac, if you have brew, you can install 'jq' with:
```
brew install jq
```

## Airflow deployment preparation

Ensure that all your airflow deployments are running on Airflow version 1.10.7

```
FROM astronomerinc/ap-airflow:1.10.7-alpine3.10-onbuild
```

## Kubernetes preparation

Ensure you are running on Kubernetes 1.14+

## Collect installation-specific information

- Namespace in which the Astronomer platform is installed (example: 'astronomer')
- Helm release name of the Astronomer platform (example: 'astronomer')
- You can confirm the namespace with
```
kubectl get pods -n <namespace here>
```
- In the above output, you should see the Astronomer platform's Pods, such as a pod with name including 'houston' and also elasticsearch pods
- You can confirm the release name with
```
helm list <release name>
```
- Above, you should have found "astronomer-platform" somewhere in the result line

## Upgrade script

- You will want to perform this step while users are not changing anything such as new deployments or deployment configuration changes
- It is recommended to pause DAGs, but it's not absolutely necessary if you can tolerate tasks failing.
- Download the 'upgrade.sh' script and execute it with two arguments: release name, and namespace (see above 'collect installation-specific information')
- This script will write some .yaml files to your local directory inside of a directory 'helm-values-backup'. These are important to back up, and can be used to restore deployments in the event that something goes wrong. These files include secrets.
- The script is interactive, so pay attention for a few questions
- If there is a failure, copy the output and report to Astronomer support
- There is one error message that might show up that can be ignored:
```
E0401 22:10:07.041224   11330 portforward.go:372] error copying from remote stream to local connection: readfrom tcp4 127.0.0.1:45835->127.0.0.1:36720: write tcp4 127.0.0.1:45835->127.0.0.1:36720: write: broken pipe
```
Above: this does not matter because it will automatically retry.

## Check that it worked

Here are a few things we can do to make sure everything worked as expected:

- Watch the pods stabilize, there should be zero crashlooping pods, and all should show 'Running' with full readiness "N/N" (not N-1 / N) or 'Completed' with 0/1 readiness
```
watch kubectl get pods -n <release namespace>
```
- Find the houston pods
```
_ kubectl get pods -n astronomer | grep houston
```
- An example output is:
```
astronomer-houston-84945966d8-jc54j                       1/1     Running     0          3d
astronomer-houston-cleanup-deployments-1580083200-p8dk5   0/1     Completed   0          21h
astronomer-houston-expire-deployments-1580083200-jxsxj    0/1     Completed   0          21h
astronomer-houston-upgrade-deployments-lw9kc              0/1     Completed   0          3d21h
```
- Note: you may not have the 0/1 pods above, depending on your configuration. Don't worry about that.
- Ensure that the database migration worked by checking the logs of the main Houston pod
```
# Use the pod name corresponding to your result of finding the houston pods
kubectl logs -n <release namespace> astronomer-houston-84945966d8-jc54j
```
- Ensure that the Airflow deployments upgrade was applied by checking the helm version of the airflow chart(s)
```
helm list | grep airflow
```
- Note: above, the results that include "airflow" should all have the same version, and the version should be the [latest published airflow chart version](https://github.com/astronomer/airflow-chart/releases), not including alpha releases or release candidates (.alpha or .rc).
- Check that all pods are running in the Airflow namespaces. If the scheduler is crashlooping with the liveness probe failing because 'airflow.jobs' module is missing, it's because you need to update Airflow Dockerfile to version
```
FROM astronomerinc/ap-airflow:1.10.7-alpine3.10-onbuild
```
- Tasks should resume normal success rate within a few minutes
- Check that you can deploy changes to Airflow, and check that the chart version remains the same after deploying an update to an Airflow (helm list | grep airflow)
