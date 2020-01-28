# Astronomer 0.11 upgrade guide


## Schedule a change window

- This upgrade will cause users to lose their Airflow secrets if they push a deployment, reconfigure a deployment, or make a new deployment while the following procedure is underway
- This procedure is expected to interrupt task execution for a few minutes on each deployment
- Scheduling 4 hours is recommended in order to Astronomer support to be able to resolve any potential issues in time. Please plan with Astronomer for support availability.

## Environment preparation

Install some command line tools:

- kubectl (version appropriate for your cluster's version)
- [helm (version 2.16.1)](https://github.com/helm/helm/releases/tag/v2.16.1)
- [jq](https://stedolan.github.io/jq/download/)

## Collect installation-specific information

- Namespace in which the Astronomer platform is installed (example: 'astronomer')
- Helm release name of the Astronomer platform (example: 'astronomer')
- You can confirm the namespace with
```
kubectl get pods -n <namespace here>
```
- In the above output, you should see the Astronomer platform's Pods
- You can confirm the release name with
```
helm list <release name>
```

## Migration script

- You will want to perform this step, then the following 'Helm upgrade' step one after the other while users are not changing anything such as new deployments or deployment configuration changes
- Clone this repository, change directory into it, and run the script
```
git clone https://github.com/astronomer/migration-script.git
cd migration-script
./pre-0-11-upgrade.sh <release name> <namespace>
```
- This script will write some .yaml files to your local directory. These are very important to back up, and can be used to restore deployments in the event that something goes wrong. These files include secrets.
- If there is a failure, copy the output and report to Astronomer support
- The point of this script is to persist helm configuration data

## Platform upgrade

- Back up the platform configuration
```
git clone https://github.com/astronomer/astronomer.git
cd astronomer
git checkout v0.11.1
helm get values <release name> > astronomer.yaml
```
- Confirm values are in astronomer.yaml
- Delete then re-install the platform
```
helm delete --purge <release name>
helm install -f ./astronomer.yaml --version "v0.11.1" --namespace <the namespace> --name <the current release name> .
```

- Check that your DNS record points to the right place
```
kubectl get svc -n <the namespace>
```
- Find the name of the LoadBalancer (e.g. a2a1d2730421911eab3e102ea6916f09-2139587190.us-east-1.elb.amazonaws.com), and make sure your domain name has a CNAME record pointing to this load balancer.

## Check that it worked

Here are a few things we can do to make sure everything worked as expected:

- Watch the pods stabilize
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
- Ensure that the database migration worked by checking the logs of the main Houston pod
```
# Use the pod name corresponding to your result of finding the houston pods
kubectl logs -n <release namespace> astronomer-houston-84945966d8-jc54j
```
- Ensure that the Airflow deployments upgrade worked (or watch it run) by checking the logs of the upgrade-deployments houston pod
```
# Use the pod name corresponding to your result of finding the houston pods
kubectl logs -f -n <release namespace> astronomer-houston-upgrade-deployments-lw9kc
```
- Ensure that the Airflow deployments upgrade worked by checking Helm
```
# all should be at 0.11.0 after the upgrade-deployments Houston pod is done (above)
helm list | grep airflow
```
- Ensure that the script in this repository did its job by going into any airflow deployment's UI, clicking "Admin" > "Variables" and making sure that the variables are still there. If you are not using Airflow secrets, it will not show any variables.
- Tasks should resume normal success rate within a few minutes
