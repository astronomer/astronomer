# Prometheus Blackbox Exporter

Prometheus exporter for blackbox testing

Learn more: [https://github.com/prometheus/blackbox_exporter](https://github.com/prometheus/blackbox_exporter)

## TL;DR;

```bash
$ helm install stable/prometheus-blackbox-exporter
```

## Introduction

This chart creates a Blackbox-Exporter deployment on a [Kubernetes](http://kubernetes.io) cluster using the [Helm](https://helm.sh) package manager.

## Prerequisites

- Kubernetes 1.8+ with Beta APIs enabled

## Installing the Chart

To install the chart with the release name `my-release`:

```bash
$ helm install --name my-release stable/prometheus-blackbox-exporter
```

The command deploys Blackbox Exporter on the Kubernetes cluster using the default configuration. The [configuration](#configuration) section lists the parameters that can be configured during installation.

## Uninstalling the Chart

To uninstall/delete the `my-release` deployment:

```bash
$ helm delete --purge my-release
```
The command removes all the Kubernetes components associated with the chart and deletes the release.

## Configuration

The following table lists the configurable parameters of the Blackbox-Exporter chart and their default values.

| Parameter                                 | Description                                                                      | Default                                                                      |
| ----------------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `kind`                                    | You can choose between `Deployment` or `DaemonSet`                               | `Deployment`                                                                 |
| `config`                                  | Prometheus blackbox configuration                                                | {}                                                                           |
| `secretConfig`                            | Whether to treat blackbox configuration as secret                                | `false`                                                                      |
| `extraArgs`                               | Optional flags for blackbox                                                      | `[]`                                                                         |
| `image.repository`                        | container image repository                                                       | `prom/blackbox-exporter`                                                     |
| `image.tag`                               | container image tag                                                              | `v0.15.1`                                                                    |
| `image.pullPolicy`                        | container image pull policy                                                      | `IfNotPresent`                                                               |
| `image.pullSecrets`                       | container image pull secrets                                                     | `[]`                                                                         |
| `ingress.annotations`                     | Ingress annotations                                                              | None                                                                         |
| `ingress.enabled`                         | Enables Ingress                                                                  | `false`                                                                      |
| `ingress.hosts`                           | Ingress accepted hostnames                                                       | None                                                                         |
| `ingress.tls`                             | Ingress TLS configuration                                                        | None                                                                         |
| `nodeSelector`                            | node labels for pod assignment                                                   | `{}`                                                                         |
| `runAsUser`                               | User to run blackbox-exporter container as                                       | `1000`                                                                       |
| `readOnlyRootFilesystem`                  | Set blackbox-exporter file-system to read-only                                   | `true`                                                                       |
| `runAsNonRoot`                            | Run blackbox-exporter as non-root                                                | `true`                                                                       |
| `tolerations`                             | node tolerations for pod assignment                                              | `[]`                                                                         |
| `affinity`                                | node affinity for pod assignment                                                 | `{}`                                                                         |
| `podAnnotations`                          | annotations to add to each pod                                                   | `{}`                                                                         |
| `podDisruptionBudget`                     | pod disruption budget                                                            | `{}`                                                                         |
| `priorityClassName`                       | priority class name                                                              | None                                                                         |
| `allowIcmp`                               | whether to enable ICMP probes, by giving the pods `CAP_NET_RAW` and running as root | `false`                                                                   |
| `resources`                               | pod resource requests & limits                                                   | `{}`                                                                         |
| `restartPolicy`                           | container restart policy                                                         | `Always`                                                                     |
| `service.annotations`                     | annotations for the service                                                      | `{}`                                                                         |
| `service.labels`                          | additional labels for the service                                                | None                                                                         |
| `service.type`                            | type of service to create                                                        | `ClusterIP`                                                                  |
| `service.port`                            | port for the blackbox http service                                               | `9115`                                                                       |
| `service.externalIPs`                     | list of external ips                                                             | []                                                                           |
| `strategy`                                | strategy used to replace old Pods with new ones                                  | `{"rollingUpdate":{"maxSurge":1,"maxUnavailable":0},"type":"RollingUpdate"}` |

Specify each parameter using the `--set key=value[,key=value]` argument to `helm install`. For example,

```bash
$ helm install --name my-release \
    --set key_1=value_1,key_2=value_2 \
    stable/prometheus-blackbox-exporter
```

Alternatively, a YAML file that specifies the values for the parameters can be provided while installing the chart. For example,

```bash
# example for staging
$ helm install --name my-release -f values.yaml stable/prometheus-blackbox-exporter
```

> **Tip**: You can use the default [values.yaml](values.yaml)

## Upgrading an existing Release to a new major version

### 2.0.0

This version removes the `podDisruptionBudget.enabled` parameter and changes the default value of `podDisruptionBudget` to `{}`, in order to fix Helm 3 compatibility.

In order to upgrade, please remove `podDisruptionBudget.enabled` from your custom values.yaml file and set the content of `podDisruptionBudget`, for example:
```yaml
podDisruptionBudget:
  maxUnavailable: 0
```

### 1.0.0

This version introduce the new recommended labels.

In order to upgrade, delete the Deployment before upgrading:
```bash
$ kubectl delete deployment my-release-prometheus-blackbox-exporter
```

Note that this will cause downtime of the blackbox.
