# Prometheus Node Exporter

* Installs prometheus [node exporter](https://github.com/prometheus/node_exporter)


## Configuration

The following table lists the configurable parameters of the Node Exporter chart and their default values.

|             Parameter                 |                                                          Description                                                          |                 Default                          |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `image.repository`                    | Image repository                                                                                                              | `quay.io/prometheus/node-exporter`               |
| `image.tag`                           | Image tag                                                                                                                     | `v1.0.1`                                         |
| `image.pullPolicy`                    | Image pull policy                                                                                                             | `IfNotPresent`                                   |
| `extraArgs`                           | Additional container arguments                                                                                                | `[]`                                             |
| `extraHostVolumeMounts`               | Additional host volume mounts                                                                                                 | `[]`                                             |
| `podAnnotations`                      | Annotations to be added to node exporter pods                                                                                 | `{}`                                             |
| `podLabels`                           | Additional labels to be added to pods                                                                                         | `{}`                                             |
| `rbac.create`                         | If true, create & use RBAC resources                                                                                          | `true`                                           |
| `resources`                           | CPU/Memory resource requests/limits                                                                                           | `{}`                                             |
| `service.type`                        | Service type                                                                                                                  | `ClusterIP`                                      |
| `service.port`                        | The service port                                                                                                              | `9100`                                           |
| `service.targetPort`                  | The target port of the container                                                                                              | `9100`                                           |
| `service.nodePort`                    | The node port of the service                                                                                                  |                                                  |
| `service.listenOnAllInterfaces`       | If true, listen on all interfaces using IP `0.0.0.0`. Else listen on the IP address pod has been assigned by Kubernetes.      | `true`                                           |
| `service.annotations`                 | Kubernetes service annotations                                                                                                | `{prometheus.io/scrape: "true"}`                 |
| `serviceAccount.create`               | Specifies whether a service account should be created.                                                                        | `true`                                           |
| `serviceAccount.name`                 | Service account to be used. If not set and `serviceAccount.create` is `true`, a name is generated using the fullname template |                                                  |
| `serviceAccount.imagePullSecrets`     | Specify image pull secrets                                                                                                    | `[]`                                             |
| `securityContext`                     | SecurityContext                                                                                                               | See values.yaml                                  |
| `affinity`                            | A group of affinity scheduling rules for pod assignment                                                                       | `{}`                                             |
| `nodeSelector`                        | Node labels for pod assignment                                                                                                | `{}`                                             |
| `tolerations`                         | List of node taints to tolerate                                                                                               | `- effect: NoSchedule operator: Exists`          |
| `priorityClassName`                   | Name of Priority Class to assign pods                                                                                         | `nil`                                            |
| `endpoints`                           | list of addresses that have node exporter deployed outside of the cluster                                                     | `[]`                                             |
| `hostNetwork`                         | Whether to expose the service to the host network                                                                             | `true`                                           |
| `prometheus.monitor.enabled`          | Set this to `true` to create ServiceMonitor for Prometheus operator                                                           | `false`                                          |
| `prometheus.monitor.additionalLabels` | Additional labels that can be used so ServiceMonitor will be discovered by Prometheus                                         | `{}`                                             |
| `prometheus.monitor.namespace`        | namespace where servicemonitor resource should be created                                                                     | `the same namespace as prometheus node exporter` |
| `prometheus.monitor.relabelings`      | Relabelings that should be applied on the ServerMonitor                                                                       | `{}` |
| `prometheus.monitor.scrapeTimeout`    | Timeout after which the scrape is ended                                                                                       | `10s`                                            |
| `configmaps`                          | Allow mounting additional configmaps.                                                                                         | `[]`                                             |
| `namespaceOverride`                   | Override the deployment namespace                                                                                             | `""` (`Release.Namespace`)                       |
| `updateStrategy`                      | Configure a custom update strategy for the daemonset                                                                          | `Rolling update with 1 max unavailable`          |
| `sidecars`               | Additional containers for export metrics to text file     | `[]`           |  |
| `sidecarVolumeMount`               | Volume for sidecar containers     | `[]`           |  |

