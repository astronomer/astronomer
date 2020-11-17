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

Ensure that all your airflow deployments are running FROM this Docker image
```
quay.io/astronomer/ap-airflow:1.10.7-alpine3.10-onbuild
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
FROM quay.io/astronomer/ap-airflow:1.10.7-alpine3.10-onbuild
```
- Tasks should resume normal success rate within a few minutes
- Check that you can deploy changes to Airflow, and check that the chart version remains the same after deploying an update to an Airflow (helm list | grep airflow)


### Migrate to helm version 3

#### Scenario 1: you already installed platform v0.13 and would like to upgrade to 0.14 and helm 3:

Check if you have all tools/plugins:
- helm (helm2)
- helm3 (helm3)

> Note: How to install helm2/helm3 and the same time:

```
which helm3
/Users/andrii/workspace/bin/helm3
which helm
/usr/local/bin/helm
```

Install helm-2to3 plugin:

```
$ helm3 plugin install https://github.com/helm/helm-2to3.git
```

Check plugins installation:

```
$ helm3 plugin list
NAME    VERSION DESCRIPTION
2to3    0.5.1   migrate and cleanup Helm v2 configuration and releases in-place to Helm v3
```


Check you have access to platform via helm 2:

```
$ helm list
NAME                    REVISION        UPDATED                         STATUS          CHART                           APP VERSION     NAMESPACE
astronomer              1               Mon Apr 27 20:14:43 2020        DEPLOYED        astronomer-0.13.0-alpha.3       0.13.0-alpha.3  astronomer
descriptive-galaxy-3178 1               Mon Apr 27 20:48:59 2020        DEPLOYED        airflow-0.13.0-alpha.2                          astronomer-descriptive-gal
```


> We must stop/ all releases from users, by disabling UI/registry/houston.


Perform Helm v2 release migration as a batch operation:

```
$ kubectl get configmap -n kube-system -l "OWNER=TILLER" \
 | awk '{print $1}' | grep -v NAME | cut -d '.' -f1 | uniq | xargs -n1 helm3 2to3 convert

# example of output:
2020/04/27 21:08:18 Release "astronomer" will be converted from Helm v2 to Helm v3.
2020/04/27 21:08:18 [Helm 3] Release "astronomer" will be created.
2020/04/27 21:08:18 [Helm 3] ReleaseVersion "astronomer.v1" will be created.
2020/04/27 21:08:18 [Helm 3] ReleaseVersion "astronomer.v1" created.
2020/04/27 21:08:18 [Helm 3] Release "astronomer" created.
2020/04/27 21:08:18 Release "astronomer" was converted successfully from Helm v2 to Helm v3.
2020/04/27 21:08:18 Note: The v2 release information still remains and should be removed to avoid conflicts with the migrated v3 release.
2020/04/27 21:08:18 v2 release information should only be removed using `helm 2to3` cleanup and when all releases have been migrated over.
2020/04/27 21:08:18 Release "descriptive-galaxy-3178" will be converted from Helm v2 to Helm v3.
2020/04/27 21:08:18 [Helm 3] Release "descriptive-galaxy-3178" will be created.
2020/04/27 21:08:18 [Helm 3] ReleaseVersion "descriptive-galaxy-3178.v1" will be created.
2020/04/27 21:08:18 [Helm 3] ReleaseVersion "descriptive-galaxy-3178.v1" created.
2020/04/27 21:08:18 [Helm 3] Release "descriptive-galaxy-3178" created.
2020/04/27 21:08:18 Release "descriptive-galaxy-3178" was converted successfully from Helm v2 to Helm v3.
2020/04/27 21:08:18 Note: The v2 release information still remains and should be removed to avoid conflicts with the migrated v3 release.
2020/04/27 21:08:18 v2 release information should only be removed using `helm 2to3` cleanup and when all releases have been migrated over.
```

Make sure now all releases helm3:
```
$ helm3 list -A
NAME                    NAMESPACE                               REVISION        UPDATED                                 STATUS          CHART                           APP VERSION
astronomer              astronomer                              1               2020-04-27 17:14:43.1608753 +0000 UTC   deployed        astronomer-0.13.0-alpha.3       0.13.0-alpha.3
descriptive-galaxy-3178 astronomer-descriptive-galaxy-3178      1               2020-04-27 17:48:59.7537798 +0000 UTC   deployed        airflow-0.13.0-alpha.2
```

Redeploy commander:
```
helm3 upgrade -n astronomer astronomer -f ./configs/local-dev.yaml --set global.postgresqlEnabled=true .
```


New commander roles:


#### Scenario 2: fresh installation of platform 0.14 using helm 3:

Assuming you have already installed helm version 3:
```
$ helm version
helm version
version.BuildInfo{Version:"v3.1.2", GitCommit:"d878d4d45863e42fd5cff6743294a11d28a9abce", GitTreeState:"clean", GoVersion:"go1.14"}
```

Installing platform:

```
$ helm install -f ./configs/local-dev.yaml --namespace astronomer -n astronomer --set global.postgresqlEnabled=true .

helm list -A
NAME            NAMESPACE       REVISION        UPDATED                                 STATUS          CHART                           APP VERSION
astronomer      astronomer      1               2020-04-27 23:54:25.700019 +0300 EEST   deployed        astronomer-0.13.0-alpha.3       0.13.0-alpha.3
```



```
$ kubectl get pods -A
NAMESPACE     NAME                                                       READY   STATUS      RESTARTS   AGE
astronomer    astronomer-astro-ui-7df8ddf49d-kdqsn                       1/1     Running     0          4m27s
astronomer    astronomer-cli-install-568897bfd8-sckxp                    1/1     Running     0          4m27s
astronomer    astronomer-commander-bcf79fd54-s4zs4                       1/1     Running     0          4m27s
astronomer    astronomer-houston-7868bbc766-99lpp                        1/1     Running     0          4m27s
astronomer    astronomer-houston-upgrade-deployments-4q6tj               0/1     Completed   0          4m26s
astronomer    astronomer-kubed-6cc48c5767-hj5sp                          1/1     Running     0          4m27s
astronomer    astronomer-nginx-765b6bfb9b-954ch                          1/1     Running     0          4m27s
astronomer    astronomer-nginx-default-backend-7956f565dd-9r76j          1/1     Running     0          4m27s
astronomer    astronomer-postgresql-0                                    1/1     Running     0          4m26s
astronomer    astronomer-prisma-7d9d7f9cc6-xsp45                         1/1     Running     0          4m27s
astronomer    astronomer-prometheus-blackbox-exporter-65f6c5f456-vpv5q   1/1     Running     0          4m27s
astronomer    astronomer-prometheus-blackbox-exporter-65f6c5f456-wt7s4   1/1     Running     0          4m27s
astronomer    astronomer-registry-0                                      1/1     Running     0          4m26s
kube-system   coredns-5c98db65d4-gjsq2                                   1/1     Running     0          4m27s
kube-system   coredns-5c98db65d4-n5j4b                                   1/1     Running     0          4m27s
kube-system   etcd-kind-control-plane                                    1/1     Running     0          3m30s
kube-system   kindnet-t4zll                                              1/1     Running     0          4m27s
kube-system   kube-apiserver-kind-control-plane                          1/1     Running     0          3m32s
kube-system   kube-controller-manager-kind-control-plane                 1/1     Running     0          3m39s
kube-system   kube-proxy-6qj2h                                           1/1     Running     0          4m27s
kube-system   kube-scheduler-kind-control-plane                          1/1     Running     0          3m30s
```
