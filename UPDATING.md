# Updating Astronomer
This guide contains information about upgrading and downgrading between Astronomer platform versions starting with `v0.6.2` -> `v0.7.0`.

## Prerequisites

Before you begin you will want to ensure that you have a copy of the `config.yaml` that you used during the last upgrade or install. This will ensure your platform configuration remains the exact same during the upgrade process.

### Checkout Desired Tag
Checkout the desired from our [helm.astronomer.io](https://github.com/astronomer/helm.astronomer.io) repository.

Ex.

```bash
git checkout v0.7.0
```

## Astronomer v0.7.0

### Upgrading the Platform

Once you have pulled the `v0.7.0` release and recovered the `config.yaml` from your previous install/upgrade, you can delete and reinstall the latest version using the following commands.

__Get platform release name__

```bash
helm ls
```

__Delete Platform Release__

```bash
helm delete [PLATFORM RELEASE]
```

__Install v0.7.0 from your helm.astronomer.io directory__

```bash
helm install -f config.yaml . --namespace [PLATFORM NAMESPACE]
```

### Upgrading Deployments

With `v0.7.x`, we have released some major changes in deployment configurability via the UI. For this release, there are some additional steps you should follow carefully to ensure your deployment configurations remain through the upgrade.

#### Capturing Deployment Configuration

For each of the following deployment components you will need to take note of the memory and CPU allocations, we suggest writing them down in a separate file. For the worker component, you will also need to take note of the # of replicas.

- webserver
- scheduler
- workers

Ex.

```bash
kubectl describe deploy/nebular-gegenschein-4079-webserver
```

#### Standard Sizes vs Custom Configuration TODO
We have pre-defined 3 different sizes which fit most of our customers' needs. If you need further customization of a resource ...

#### Perform Deployment Upgrade
You will now be able to safely upgrade the deployment by navigating to the deployment settings and configuration view in the web UI and clicking the upgrade button. You will then be prompted, letting you know that an upgrade will require a reboot, if you are okay with a reboot, click `yes`. Behind the scenes we will now run a `helm upgrade` against your deployment in order to enable the `v0.7.x` features.

#### Setting Deployment Configuration
Now that you have captured the deployment configuration and upgraded the deployment, you can adjust the sliders in the deployment configuration/settings panel to match the settings you recorded above. Once you are satisfied with the configuration, press `update` to allow the new configuration to take place.

### Downgrading
In some instances, you may want to perform a downgrade of the platform back to the previous version.

#### Capture Houston Backend Secret

`export HOUSTON_POSTGRES_URI=$(kbl get secret {PLATFORM RELEASE NAME}-houston-backend -o json | jq ".data.connection" -r | base64 --decode)`

#### Launch Pod to Perform Downgrade

```bash
kubectl run houston-command-zombie -it --image=astronomerinc/ap-houston-api \
  --stdin=true --restart=OnFailure --rm \
  --env "HOUSTON_POSTGRES_URI=$(echo $HOUSTON_POSTGRES_URI)" \
  --command -- env
```
