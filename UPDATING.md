# Updating Astronomer
This guide contains information about upgrading and downgrading between Astronomer platform versions starting with `v0.6.2` -> `v0.7.1`.

## Prerequisites

Before you begin you will want to ensure that you have a copy of the `config.yaml` that you used during the last upgrade or install. This will ensure your platform configuration remains the exact same during the upgrade process.

### Checkout Desired Tag
Checkout the desired from our [helm.astronomer.io](https://github.com/astronomer/helm.astronomer.io) repository.

Ex.

```bash
git fetch && git checkout v0.7.1
```

## Astronomer v0.7.1

### Upgrading the Platform

Once you have pulled the `v0.7.1` release and recovered the `config.yaml` from your previous install/upgrade, you can delete and reinstall the latest version using the following commands.

**Note** You must specify the same platform release name that was used previously. If you do not see your deployments after an upgrade, it is likely due to failure to specify the `-n` arg on the install. If you see this, attempt to do another `helm delete` and `install`, this time specifying the release name.

__Get platform release name__

```bash
helm ls
```

__Delete Platform Release__

```bash
helm delete --purge [PLATFORM RELEASE NAME]
```

__Install v0.7.1 from your helm.astronomer.io directory__

```bash
helm install -f config.yaml . -n [PLATFORM RELEASE NAME] --namespace [PLATFORM NAMESPACE]
```

### Upgrading Deployments

With v0.7.x, we have released some major changes in deployment configurability via the UI. For this release, there are some additional steps you should follow carefully to ensure your deployment configurations remain through the upgrade.

#### Capturing Deployment Configuration

For each of the following deployment components you will need to take note of the memory and CPU allocations, we suggest writing them down in a separate file. For the worker component, you will also need to take note of the # of replicas. In the below command worker replicas will be shown by multiple components with 'worker' in the name.

Here is a kubectl command to output resources of all pods in a namespace.

```
kubectl get pods \
     -o=jsonpath='{"NAME"}{"\t\t\t\t\t\tLIMITS"}{"\t\t\t\t\tREQUESTS\n"}{range .items[*]}{ range .spec.containers[*]}{.name}{"\t\t"}{.resources.limits}{"\t\t"}{.resources.requests}{"\n"}{end}{end}' \
    --namespace [DEPLOYMENT NAMESPACE]
```

#### Scale Workers Down To 0
To help improve the speed of the upgrade process, scale your workers down to zero by editing the worker statefuleset.

Run `kubectl get statefulsets` to get the name of your worker statefulset and `kubectl edit statefulset [STATEFUL SET NAME]` to edit the configuration.

You can then modify the `spec.replicas` attribute to be 0. Save and close. Please wait until all workers are spun down before continuing to the next step. You can monitor the spindown process with `kubectl get pods`.

#### Perform Deployment Upgrade
You will now be able to safely upgrade the deployment by navigating to the deployment settings and configuration view in the web UI and clicking the upgrade button. Behind the scenes we will now run a `helm upgrade` against your deployment in order to enable the v0.7.x features.

#### Setting Deployment Configuration
Now that you have captured the deployment configuration and upgraded the deployment, you can adjust the sliders in the deployment configuration/settings panel to match the settings you recorded above. Once you are satisfied with the configuration, press `update` to allow the new configuration to take place.

#### Rebooting Statsd-exporter
Since helm doesn't give us much control over ordering of deployments, a race condition exists between the scheduler and statsd pod boot order. If a deployment is showing "Scheduler Heartbeat" as "Unhealthy" on the "Airflow Deployment Overview" dashboard in Grafana, just delete the statsd exporter pod and let kubernetes recreate it. The scheduler heartbeat should start to rise and report "Healthy".
