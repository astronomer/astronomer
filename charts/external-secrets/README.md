# External Secrets

<p><img src="https://raw.githubusercontent.com/external-secrets/external-secrets/main/assets/eso-logo-large.png" width="100x"  alt="external-secrets"></p>

This is a hard fork of the public external-secrets chart tailored for APC use cases.

### Custom Resources

By default, the chart will install external-secrets CRDs on each upgrade.

## Values

The blow list is not 100% accurate after the hard fork. Effort has been put into removing items that were removed from the chart.

| Key                         | Type   | Default                         | Description                         |
| ------------------ | ------ | ---------------------------------------- | ---------------------------------------------------------- |
| affinity                         | object | `{}`                         |                         |
| commonLabels                         | object | `{}`                         | Additional labels added to all helm chart resources.                         |
| concurrent                         | int    | `1`                         | Specifies the number of concurrent ExternalSecret Reconciles external-secret executes at a time.                         |
| controllerClass                         | string | `""`                         | If set external secrets will filter matching Secret Stores with the appropriate controller values.                         |
| crds.annotations                         | object | `{}`                         |                         |
| crds.conversion.enabled                         | bool   | `false`                         | Conversion is disabled by default as we stopped supporting v1alpha1.                         |
| deploymentAnnotations                         | object | `{}`                         | Annotations to add to Deployment                         |
| dnsConfig                         | object | `{}`                         | Specifies `dnsOptions` to deployment                         |
| dnsPolicy                         | string | `"ClusterFirst"`                         | Specifies `dnsPolicy` to deployment                         |
| extendedMetricLabels                         | bool   | `false`                         | If true external secrets will use recommended kubernetes annotations as prometheus metric labels.                         |
| extraArgs                         | object | `{}`                         |                         |
| extraContainers                         | list   | `[]`                         |                         |
| extraEnv                         | list   | `[]`                         |                         |
| extraInitContainers                         | list   | `[]`                         |                         |
| extraObjects                         | list   | `[]`                         |                         |
| extraVolumeMounts                         | list   | `[]`                         |                         |
| extraVolumes                         | list   | `[]`                         |                         |
| fullnameOverride                         | string | `""`                         |                         |
| genericTargets                         | object | `{"enabled":false,"resources":[]}`                         | Enable support for generic targets (ConfigMaps, Custom Resources). Warning: Using generic target. Make sure access policies and encryption are properly configured. When enabled, this grants the controller permissions to create/update/delete ConfigMaps and optionally other resource types specified in generic.resources. |
| genericTargets.enabled                         | bool   | `false`                         | Enable generic target support                         |
| genericTargets.resources                         | list   | `[]`                         | List of additional resource types to grant permissions for. Each entry should specify apiGroup, resources, and verbs. Example: resources: - apiGroup: "argoproj.io" resources: ["applications"] verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]                         |
| global.affinity                         | object | `{}`                         |                         |
| global.compatibility.openshift.adaptSecurityContext | string | `"auto"`                         | Manages the securityContext properties to make them compatible with OpenShift. Possible values: auto - Apply configurations if it is detected that OpenShift is the target platform. force - Always apply configurations. disabled - No modification applied.                         |
| global.hostAliases                         | list   | `[]`                         | Global hostAliases to be applied to all deployments                         |
| global.imagePullSecrets                         | list   | `[]`                         | Global imagePullSecrets to be applied to all deployments                         |
| global.nodeSelector                         | object | `{}`                         |                         |
| global.podAnnotations                         | object | `{}`                         | Global pod annotations to be applied to all deployments                         |
| global.podLabels                         | object | `{}`                         | Global pod labels to be applied to all deployments                         |
| global.repository                         | string | `""`                         | Global image repository to be applied to all deployments                         |
| global.tolerations                         | list   | `[]`                         |                         |
| global.topologySpreadConstraints                    | list   | `[]`                         |                         |
| hostAliases                         | list   | `[]`                         | Specifies `hostAliases` to deployment                         |
| hostNetwork                         | bool   | `false`                         | Run the controller on the host network                         |
| hostUsers                         | bool   | `nil`                         | Specifies if controller pod should use hostUsers or not. If hostNetwork is true, hostUsers should be too. Only available in Kubernetes ≥ 1.33. @schema type: [boolean, null]                         |
| image.flavour                         | string | `""`                         | The flavour of tag you want to use There are different image flavours available, like distroless and ubi. Please see GitHub release notes for image tags for these flavors. By default, the distroless image is used.                         |
| image.pullPolicy                         | string | `"IfNotPresent"`                         |                         |
| image.repository                         | string | `"ghcr.io/external-secrets/external-secrets"`                         |                         |
| image.tag                         | string | `""`                         | The image tag to use. The default is the chart appVersion.                         |
| imagePullSecrets                         | list   | `[]`                         |                         |
| installCRDs                         | bool   | `true`                         | If set, install and upgrade CRDs through helm chart.                         |
| leaderElect                         | bool   | `false`                         | If true, external-secrets will perform leader election between instances to ensure no more than one instance of external-secrets operates at a time.                         |
| livenessProbe.enabled                         | bool   | `false`                         | Enabled determines if the liveness probe should be used or not. By default it's disabled.                         |
| livenessProbe.spec                         | object | `{"address":"","failureThreshold":5,"httpGet":{"path":"/healthz","port":"live"},"initialDelaySeconds":10,"periodSeconds":10,"port":8082,"successThreshold":1,"timeoutSeconds":5}` | The body of the liveness probe settings.                         |
| livenessProbe.spec.address                         | string | `""`                         | Bind address for the health server used by both liveness and readiness probes (--live-addr flag).                         |
| livenessProbe.spec.failureThreshold                 | int    | `5`                         | Number of consecutive probe failures that should occur before considering the probe as failed.                         |
| livenessProbe.spec.httpGet                         | object | `{"path":"/healthz","port":"live"}`                         | Handler for liveness probe.                         |
| livenessProbe.spec.httpGet.path                     | string | `"/healthz"`                         | Path for liveness probe.                         |
| livenessProbe.spec.httpGet.port                     | string | `"live"`                         | Set this value to 'live' (for named port) or an an integer for liveness probes. @schema type: [string, integer]                         |
| livenessProbe.spec.initialDelaySeconds              | int    | `10`                         | Delay in seconds for the container to start before performing the initial probe.                         |
| livenessProbe.spec.periodSeconds                    | int    | `10`                         | Period in seconds for K8s to start performing probes.                         |
| livenessProbe.spec.port                         | int    | `8082`                         | Port for the health server used by both liveness and readiness probes (--live-addr flag).                         |
| livenessProbe.spec.successThreshold                 | int    | `1`                         | Number of successful probes to mark probe successful.                         |
| livenessProbe.spec.timeoutSeconds                   | int    | `5`                         | Specify the maximum amount of time to wait for a probe to respond before considering it fails.                         |
| log                         | object | `{"level":"info","timeEncoding":"epoch"}`                         | Specifies Log Params to the External Secrets Operator                         |
| metrics.listen.port                         | int    | `8080`                         |                         |
| metrics.listen.secure.certDir                       | string | `"/etc/tls"`                         | TLS cert directory path                         |
| metrics.listen.secure.certFile                      | string | `"/etc/tls/tls.crt"`                         | TLS cert file path                         |
| metrics.listen.secure.enabled                       | bool   | `false`                         |                         |
| metrics.listen.secure.keyFile                       | string | `"/etc/tls/tls.key"`                         | TLS key file path                         |
| metrics.service.annotations                         | object | `{}`                         | Additional service annotations                         |
| metrics.service.enabled                         | bool   | `false`                         | Enable if you use another monitoring tool than Prometheus to scrape the metrics                         |
| metrics.service.port                         | int    | `8080`                         | Metrics service port to scrape                         |
| nameOverride                         | string | `""`                         |                         |
| namespaceOverride                         | string | `""`                         |                         |
| nodeSelector                         | object | `{}`                         |                         |
| openshiftFinalizers                         | bool   | `true`                         | If true the OpenShift finalizer permissions will be added to RBAC                         |
| podAnnotations                         | object | `{}`                         | Annotations to add to Pod                         |
| podDisruptionBudget                         | object | `{"enabled":false,"minAvailable":1,"nameOverride":""}`                         | Pod disruption budget - for more details see https://kubernetes.io/docs/concepts/workloads/pods/disruptions/                         |
| podLabels                         | object | `{}`                         |                         |
| podSecurityContext.enabled                         | bool   | `true`                         |                         |
| podSpecExtra                         | object | `{}`                         | Any extra pod spec on the deployment                         |
| priorityClassName                         | string | `""`                         | Pod priority class name.                         |
| processClusterExternalSecret                        | bool   | `true`                         | if true, the operator will process cluster external secret. Else, it will ignore them. When enabled, this adds update/patch permissions on namespaces to handle finalizers for proper cleanup during namespace deletion, preventing race conditions with ExternalSecrets.                         |
| processClusterGenerator                         | bool   | `true`                         | if true, the operator will process cluster generator. Else, it will ignore them.                         |
| processClusterPushSecret                         | bool   | `true`                         | if true, the operator will process cluster push secret. Else, it will ignore them.                         |
| processClusterStore                         | bool   | `true`                         | if true, the operator will process cluster store. Else, it will ignore them.                         |
| processPushSecret                         | bool   | `true`                         | if true, the operator will process push secret. Else, it will ignore them.                         |
| processSecretStore                         | bool   | `true`                         | if true, the operator will process secret store. Else, it will ignore them.                         |
| rbac.aggregateToEdit                         | bool   | `true`                         | Specifies whether permissions are aggregated to the edit ClusterRole                         |
| rbac.aggregateToView                         | bool   | `true`                         | Specifies whether permissions are aggregated to the view ClusterRole                         |
| rbac.create                         | bool   | `true`                         | Specifies whether role and rolebinding resources should be created.                         |
| rbac.servicebindings.create                         | bool   | `true`                         | Specifies whether a clusterrole to give servicebindings read access should be created.                         |
| readinessProbe.enabled                         | bool   | `false`                         | Determines whether the readiness probe is enabled. Disabled by default. Enabling this will auto-start the health server (--live-addr) even if livenessProbe is disabled. Health server address/port are configured via livenessProbe.spec.address and livenessProbe.spec.port.                         |
| readinessProbe.spec                         | object | `{"failureThreshold":3,"httpGet":{"path":"/readyz","port":"live"},"initialDelaySeconds":10,"periodSeconds":10,"successThreshold":1,"timeoutSeconds":5}`                         | The body of the readiness probe settings (standard Kubernetes probe spec).                         |
| readinessProbe.spec.failureThreshold                | int    | `3`                         | Number of consecutive probe failures that should occur before considering the probe as failed.                         |
| readinessProbe.spec.httpGet                         | object | `{"path":"/readyz","port":"live"}`                         | Handler for readiness probe.                         |
| readinessProbe.spec.httpGet.path                    | string | `"/readyz"`                         | Path for readiness probe.                         |
| readinessProbe.spec.httpGet.port                    | string | `"live"`                         | Set this value to 'live' (for named port) or an integer for readiness probes. @schema type: [string, integer]                         |
| readinessProbe.spec.initialDelaySeconds             | int    | `10`                         | Delay in seconds for the container to start before performing the initial probe.                         |
| readinessProbe.spec.periodSeconds                   | int    | `10`                         | Period in seconds for K8s to start performing probes.                         |
| readinessProbe.spec.successThreshold                | int    | `1`                         | Number of successful probes to mark probe successful.                         |
| readinessProbe.spec.timeoutSeconds                  | int    | `5`                         | Specify the maximum amount of time to wait for a probe to respond before considering it fails.                         |
| replicaCount                         | int    | `1`                         |                         |
| resources                         | object | `{}`                         |                         |
| revisionHistoryLimit                         | int    | `10`                         | Specifies the amount of historic ReplicaSets k8s should keep (see https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#clean-up-policy)                         |
| scopedNamespace                         | string | `""`                         | If set external secrets are only reconciled in the provided namespace                         |
| scopedRBAC                         | bool   | `false`                         | Must be used with scopedNamespace. If true, create scoped RBAC roles under the scoped namespace and implicitly disable cluster stores and cluster external secrets                         |
| securityContext.allowPrivilegeEscalation            | bool   | `false`                         |                         |
| securityContext.capabilities.drop[0]                | string | `"ALL"`                         |                         |
| securityContext.enabled                         | bool   | `true`                         |                         |
| securityContext.readOnlyRootFilesystem              | bool   | `true`                         |                         |
| securityContext.runAsNonRoot                        | bool   | `true`                         |                         |
| securityContext.runAsUser                         | int    | `1000`                         |                         |
| securityContext.seccompProfile.type                 | string | `"RuntimeDefault"`                         |                         |
| service.ipFamilies                         | list   | `[]`                         | Sets the families that should be supported and the order in which they should be applied to ClusterIP as well. Can be IPv4 and/or IPv6.                         |
| service.ipFamilyPolicy                         | string | `""`                         | Set the ip family policy to configure dual-stack see [Configure dual-stack](https://kubernetes.io/docs/concepts/services-networking/dual-stack/#services)                         |
| serviceAccount.annotations                         | object | `{}`                         | Annotations to add to the service account.                         |
| serviceAccount.automount                         | bool   | `true`                         | Automounts the service account token in all containers of the pod                         |
| serviceAccount.create                         | bool   | `true`                         | Specifies whether a service account should be created.                         |
| serviceAccount.extraLabels                         | object | `{}`                         | Extra Labels to add to the service account.                         |
| serviceAccount.name                         | string | `""`                         | The name of the service account to use. If not set and create is true, a name is generated using the fullname template.                         |
| strategy                         | object | `{}`                         | Set deployment strategy                         |
| systemAuthDelegator                         | bool   | `false`                         | If true the system:auth-delegator ClusterRole will be added to RBAC                         |
| tolerations                         | list   | `[]`                         |                         |
| topologySpreadConstraints                         | list   | `[]`                         |                         |
