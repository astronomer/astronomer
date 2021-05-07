# Astronomer upgrade guide

The Astronomer upgrade will run in a pod in the cluster.

# Before you upgrade

## Check version compatibility

- Kubernetes version must be greater than or equal to 1.14 and less than 1.19. If you need help to upgrade, please contact your cloud provider's support or your Kubernetes administrator.
- You must be using Astronomer Certified Airflow images, and your version must be 1.10.5 or greater. These images are in the form:

```
astronomerinc/ap-airflow:<airflow-version>-<build number>-<distribution>-onbuild
```

The "onbuild" part is optional, but recommended. This enables features in the astro-cli, such as using requirements.txt and packages.txt. The "build number" part is optional but recommended. Excluding the build number will reference a mutable Docker image that is occasionally replaced with underlying pip modules updated, this is typically not preferred and instead it's best to plan when updates will occur in your Docker image. If you have your own build, test, and publish workflows that are layered on top of the Astronomer Airflow images, then it is appropriate to use the mutable image.

Valid examples:

```
astronomerinc/ap-airflow:1.10.12-1-alpine3.10-onbuild
astronomerinc/ap-airflow:1.10.12-1-alpine3.10
astronomerinc/ap-airflow:1.10.5-9-buster-onbuild
astronomerinc/ap-airflow:1.10.5-9-buster
```

This is an example of a legacy images that should _not_ be used:

```
astronomerinc/ap-airflow:<astronomer version>-<airflow version>
astronomerinc/ap-airflow:
```

## Check permissions

You should be an Astronomer admin to perform the upgrade. This can be confirmed if you have access Grafana: https://grafana.your-base-domain.com or by checking that you have access to the "system admin" feature in Astronomer UI.

You will be creating Kubernetes resources to perform this upgrade. Kubernetes permission can be validated with:

```
kubectl auth can-i create pods --namespace <your astronomer namespace>
kubectl auth can-i create sa --namespace <your astronomer namespace>
kubectl auth can-i create jobs --namespace <your astronomer namespace>
```

All lines should say "yes".

## Take an external DB backup

Backup your database using your cloud provider's tool or make a request to your database administrator.

## Check on the status of your pods

All pods should be "Running" or "Completed". If you have any pods that are crashing but this is expected for some reason and you want to proceed anyways, then make note of which pods are crashing before the upgrade has been performed.

# Upgrade

Ensure that you have the default namespace in your kubernetes context, not necessarily the namespace in which Astronomer is install.

## Run the Astronomer upgrade automation

```
kubectl apply -f https://raw.githubusercontent.com/astronomer/astronomer/master/migrations/scripts/lts-to-lts/0.16-to-0.23/manifests/upgrade-0.16-to-0.23.yaml
```

Watch the logs of the upgrade pod, you can find pod name with:

```
kubectl get pods -n <your astronomer namespace> | grep lts-upgrade
```

## Validate your upgrade worked

- Navigate to your basedomain, at the /logout path
- You may need to wait up to two minutes for log in to be ready after performing an upgrade
- Validate log in works
- Validate workspaces and deployments show up in the UI
- Validate you can view the settings of an Airflow deployment
- Validate you can see metrics in the metrics tab
- Validate you can access an Airflow UI
- Validate you can do "astro deploy"
- Validate you can see logs in the Airflow UI

# Rollback

If the upgrade has some issues and you need to recover, you can rollback to the previous state

## Apply the rollback automation

```
kubectl apply -f https://raw.githubusercontent.com/astronomer/astronomer/master/migrations/scripts/lts-to-lts/0.16-to-0.23/manifests/rollback-0.16-to-0.23.yaml
```

## Wait for platform to come back up

Watch the pods until they have stabilized. Everything in your Astronomer namespace should be Running with full readiness, or Completed:

```
watch kubectl get pods -n <your namespace>
```
