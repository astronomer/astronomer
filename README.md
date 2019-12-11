# Astronomer Platform Helm Charts

[![CircleCI](https://circleci.com/gh/astronomer/helm.astronomer.io.svg?style=svg)](https://circleci.com/gh/astronomer/helm.astronomer.io)

This repository contains the helm charts for deploying the [Astronomer Platform](https://github.com/astronomer/astronomer) into a Kubernetes cluster.

Astronomer is a commercial "Airflow as a Service" platform that runs on Kubernetes. Source code is made available for the benefit of our customers, if you'd like to use the platform [reach out for a license](https://www.astronomer.io/enterprise/) or try out [Astronomer Cloud](https://www.astronomer.io/cloud/).

## Architecture

![Astronomer Architecture](https://assets2.astronomer.io/main/enterpriseArchitecture.svg "Astronomer Architecture")

## Docker images

Docker images for deploying and running Astronomer are currently available on
[DockerHub](https://hub.docker.com/u/astronomerinc/).

## Documentation

The Astronomer Platform documentation is located at https://www.astronomer.io/docs/

## Contributing

We welcome any contributions:

* Report all enhancements, bugs, and tasks as [GitHub issues](https://github.com/astronomerio/helm.astronomer.io/issues)
* Provide fixes or enhancements by opening pull requests in Github

## Local Development

Install the following tools:

- docker (make sure your user has permissions - try 'docker ps')
- kubectl
- [kind](https://github.com/kubernetes-sigs/kind#installation-and-usage)
- gcloud cli (make sure gsutil in PATH)
- helm

Make sure you have access to the GCP development account

```
# Check that you can download the development TLS cert:
gsutil cat gs://astronomer-development-certificates/fullchain.pem
```
If this does not work, anyone with 'Owner' in the development project can grant you 'Owner' via IAM.

Run this script from the root of this repository:

```
bin/reset-local-dev
```

Each time you run the script, the platform will be fully reset to the current helm chart.

### Customizing the local deployment

#### Turn on or off parts of the platform

Modify the "tags:" in configs/local-dev.yaml
- platform: core Astronomer components
- logging (large impact on RAM use): ElasticSearch, Kibana, Fluentd (aka 'EFK' stack)
- monitoring: Prometheus
- kubed: leave on

#### Add a Docker image into KinD's nodes (so it's available for pods):
```
kind load docker-image <your local image tag>
```

#### Make use of that image:

Make note of your pod name
```
kubectl get pods -n astronomer
```

Find the corresponding deployment, daemonset, or statefulset
```
kubectl get deployment -n astronomer
```

Replace the pod with the new image
Look for "image" on the appropriate container and replace with the local tag,
and set the pull policy to never.
```
kubectl edit deployment -n astronomer <your deployment>
```

#### Change Kubernetes version:
```
export KUBE_VERSION='v1.16.3'
bin/reset-local-dev
```


## Releasing

[Releasing Guide](https://github.com/astronomerio/helm.astronomer.io/blob/master/RELEASING.md)

## License

Usage of Astronomer code requires an [Astronomer Platform Enterprise Edition license](https://github.com/astronomer/astronomer/blob/master/LICENSE).
