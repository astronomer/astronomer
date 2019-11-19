# Apache Airflow

[Airflow](https://airflow.apache.org/) is a platform to programmatically author, schedule and monitor workflows.

## TL;DR

```console
$ cd charts/airflow
$ helm dependency update
$ helm install .
```

## Introduction

This chart will bootstrap an [Airfow](https://github.com/astronomer/astronomer/tree/master/docker/airflow) deployment on a [Kubernetes](http://kubernetes.io) cluster using the [Helm](https://helm.sh) package manager.

## Prerequisites

- Kubernetes 1.12+
- Helm 2.11+ or Helm 3.0-beta3+
- PV provisioner support in the underlying infrastructure

## Installing the Chart
To install the chart with the release name `my-release`:

```console
$ helm install --name my-release .
```

The command deploys Airflow on the Kubernetes cluster in the default configuration. The [Parameters](#parameters) section lists the parameters that can be configured during installation.

> **Tip**: List all releases using `helm list`

## Upgrading the Chart
To upgrade the chart with the release name `my-release`:

```console
$ helm upgrade --name my-release .
```

## Uninstalling the Chart

To uninstall/delete the `my-release` deployment:

```console
$ helm delete my-release
```

The command removes all the Kubernetes components associated with the chart and deletes the release.

## Updating DAGs
The recommended way to update your DAGs with this chart is to build a new docker image with the latest code and update the Airflow pods with that image. After your docker image is built and pushed to an accessible registry, you can update a release with:

```console
$ helm upgrade my-release . --set images.airflow.repository=my-company/airflow --set images.airflow.tag=8a0da78
```

## Parameters

The following tables lists the configurable parameters of the Airflow chart and their default values.

| Parameter                           | Description                                                                                                  | Default                                           |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------- |
| `uid`                               | UID to run airflow pods under                                                                                | `nil`                                             |
| `gid`                               | GID to run airflow pods under                                                                                | `nil`                                             |
| `nodeSelector`                      | Node labels for pod assignment                                                                               | `{}`                                              |
| `affinity`                          | Affinity labels for pod assignment                                                                           | `{}`                                              |
| `tolerations`                       | Toleration labels for pod assignment                                                                         | `[]`                                              |
| `labels`                            | Common labels to add to all objects defined in this chart                                                    | `{}`                                              |
| `privateRegistry.enabled`           | Enable usage of a private registry for Airflow base image                                                    | `false`                                           |
| `privateRegistry.repository`        | Repository where base image lives (eg: quay.io)                                                              | `~`                                               |
| `ingress.enabled`                   | Enable Kubernetes Ingress support                                                                            | `false`                                           |
| `ingress.acme`                      | Add acme annotations to Ingress object                                                                       | `false`                                           |
| `ingress.tlsSecretName`             | Name of secret that contains a TLS secret                                                                    | `~`                                               |
| `ingress.baseDomain`                | Base domain for VHOSTs                                                                                       | `~`                                               |
| `ingress.class`                     | Ingress class to associate with                                                                              | `nginx`                                           |
| `ingress.auth.enabled`              | Enable auth with Astronomer Platform                                                                         | `true`                                            |
| `networkPolicies.enabled`           | Enable Network Policies to restrict traffic                                                                  | `true`                                            |
| `airflowHome`                       | Location of airflow home directory                                                                           | `/usr/local/airflow`                              |
| `rbacEnabled`                       | Deploy pods with Kubernets RBAC enabled                                                                      | `true`                                            |
| `airflowVersion`                    | Default Airflow image version                                                                                | `1.10.5`                                          |
| `executor`                          | Airflow executor (eg SequentialExecutor, LocalExecutor, CeleryExecutor, KubernetesExecutor)                  | `KubernetesExecutor`                              |
| `allowPodLaunching`                 | Allow airflow pods to talk to Kubernetes API to launch more pods                                             | `true`                                            |


Specify each parameter using the `--set key=value[,key=value]` argument to `helm install`. For example,

```console
$ helm install --name my-release \
    --set executor=CeleryExecutor \
    --set enablePodLaunching=false .
```
