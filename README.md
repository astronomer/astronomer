# Astronomer Platform Helm Charts

This repository contains the helm charts for deploying the [Astronomer Platform](https://github.com/astronomer/astronomer) into a Kubernetes cluster.

Astronomer is a commercial "Airflow as a Service" platform that runs on Kubernetes. Source code is made available for the benefit of our customers, if you'd like to use the platform [reach out for a license](https://www.astronomer.io/get-astronomer).

## Architecture

![Astronomer Architecture](https://assets2.astronomer.io/main/enterpriseArchitecture.svg "Astronomer Architecture")

## Docker images

Docker images for deploying and running Astronomer are currently available on
[Quay.io/Astronomer](https://quay.io/organization/astronomer).

## Documentation

You can read the Astronomer platform documentation at https://docs.astronomer.io/enterprise. For a record of all user-facing changes to the Astronomer platform, see [Release Notes](https://docs.astronomer.io/enterprise/release-notes).

## Contributing

We welcome any contributions:

* Report all enhancements, bugs, and tasks as [GitHub issues](https://github.com/astronomerio/helm.astronomer.io/issues)
* Provide fixes or enhancements by opening pull requests in GitHub

## Local Development

Install the following tools:

- docker (make sure your user has permissions - try 'docker ps')
- kubectl
- [kind](https://github.com/kubernetes-sigs/kind#installation-and-usage)
- [mkcert](https://github.com/FiloSottile/mkcert) (make sure mkcert in PATH)
- helm

Run this script from the root of this repository:

```sh
bin/reset-local-dev
```

Each time you run the script, the platform will be fully reset to the current helm chart.

### Customizing the local deployment

#### Turn on or off parts of the platform

Modify the "tags:" in configs/local-dev.yaml
- platform: core Astronomer components
- logging (large impact on RAM use): ElasticSearch, Kibana, Fluentd (aka 'EFK' stack)
- monitoring: Prometheus

#### Add a Docker image into KinD's nodes (so it's available for pods):

```sh
kind load docker-image $your_local_image_name_with_tag
```

#### Make use of that image:

Make note of your pod name

```sh
kubectl get pods -n astronomer
```

Find the corresponding deployment, daemonset, or statefulset

```sh
kubectl get deployment -n astronomer
```

Replace the pod with the new image
Look for "image" on the appropriate container and replace with the local tag,
and set the pull policy to "Never".

```sh
kubectl edit deployment -n astronomer <your deployment>
```

#### Change Kubernetes version:

```sh
bin/reset-local-dev -K 1.21.2
```

#### Locally test HA configurations:

You need a powerful computer to run the HA testing locally. 28 GB or more of memory should be available to Docker.

Environment variables:

- USE_HA: when set, will deploy using HA configurations
- CORDON_NODE: when set, will cordon this node after kind create cluster
- MULTI_NODE: when set, will deploy kind with two worker nodes

Scripts:

- Use bin/run-ci to start the cluster
- Modify / use bin/drain.sh to test draining

Example:

```sh
export USE_HA=1
export CORDON_NODE=kind-worker
export MULTI_NODE=1
bin/run-ci
```

After the platform is up, then do

```sh
bin/drain.sh
```

#### How to upgrade airflow chart json schema
Every time we upgrade the airflow chart we will also need to update the json schema file with the list of acceptable top level params (eventually this will be fixed on the OSS side but for now this needs to be a manual step https://github.com/astronomer/issues/issues/3774). Additionally the json schema url will need to be updated to something of the form https://raw.githubusercontent.com/apache/airflow/helm-chart/1.x.x/chart/values.schema.json. This param is found in astronomer/values.schema.json at the astronomer.houston.config.deployments.helm.airflow.$ref parameter

To get a list of the top level params it is best to switch to the apache/airflow tagged commit for that chart release. Then run the ag command to get a list of all top level params.

Example:

```
gch tags/helm-chart/1.2.0
ag "\.Values\.\w+" -o --no-filename --no-numbers | sort | uniq
```

The values output by this command will need to be inserted manually into astronomer/values.schema.json at the `astronomer.houston.config.deployments.helm.airflow.allOf` parameter. There are two additional params that need to be at this location outside of what is returned from above. They are `podMutation` and `useAstroSecurityManager`. These can be found by running the same ag command against the astronomer/airflow-chart values.yaml file.

## License

The code in this repo is licensed Apache 2.0 with Commons Clause, however it installs Astronomer components that have a commercial license, and requires a commercial subscription from Astronomer, Inc.

## Optional schema validation

The ./values.schema.json.example file can be used to validate the helm values you are using work with the default airflow chart shipped with this repo. To use it remove the .example postfix from the file and proceed with the helm lint, install, and upgrade commands as normal.
