# Feature flag configuration path migration

This document maps every relocated Helm value from the previous scattered layout to the new structure directly under `global.*`. Use it when upgrading custom `values.yaml` overrides to the current chart version.

## Why this changed

Feature flags were previously spread across `global` with inconsistent naming (boolean suffixes like `rbacEnabled`, nested objects like `authSidecar`, standalone booleans like `namespaceFreeFormEntry`). They now use a consistent `enabled` boolean pattern with domain-grouped nesting that mirrors Houston's `default.yaml` schema. The intermediate `global.features.*` key was removed to keep Helm values aligned with Houston's config paths.

## Migration table

### Simple feature flags (directly under global)

| Old path | New path |
|---|---|
| `global.rbacEnabled` | `global.rbac.enabled` |
| `global.sccEnabled` | `global.scc.enabled` |
| `global.openshiftEnabled` | `global.openshift.enabled` |
| `global.networkPolicy.enabled` | `global.networkPolicy.enabled` (unchanged) |
| `global.networkNSLabels` | `global.networkNSLabels.enabled` |
| `global.authSidecar.*` | `global.authSidecar.*` (unchanged) |

### Domain-grouped features

These features are nested under domain groups that mirror the Houston API config schema.

| Old path | New path | Houston domain group |
|---|---|---|
| `global.namespaceFreeFormEntry` | `global.namespaceManagement.namespaceFreeFormEntry.enabled` | `deployments.namespaceManagement` |
| `global.namespacePools.*` | `global.namespaceManagement.namespacePools.*` | `deployments.namespaceManagement` |
| `global.taskUsageMetricsEnabled` | `global.metricsReporting.taskUsageMetrics.enabled` | `deployments.metricsReporting` |
| `global.deployRollbackEnabled` | `global.deploymentLifecycle.deployRollback.enabled` | `deployments.deploymentLifecycle` |
| `global.dagOnlyDeployment.*` | `global.deployMechanisms.dagOnlyDeployment.*` | `deployments.deployMechanisms` |
| `global.loggingSidecar.*` | `global.logging.loggingSidecar.*` | `deployments.logging` |

### Houston configmap output changes

The rendered Houston configuration (`production.yaml` inside the Houston ConfigMap) also changed. If you parse or assert against its structure:

| Old output path | New output path |
|---|---|
| `deployments.dagOnlyDeployment` (boolean) | `deployments.deployMechanisms.dagOnlyDeployment.enabled` |
| `deployments.namespaceFreeFormEntry` (boolean) | `deployments.namespaceManagement.namespaceFreeFormEntry.enabled` |
| `deployments.hardDeleteDeployment` (boolean) | `deployments.namespaceManagement.hardDeleteDeployment.enabled` |
| `deployments.manualNamespaceNames` (boolean) | `deployments.namespaceManagement.manualNamespaceNames.enabled` |
| `deployments.namespaceLabels` | `deployments.namespaceManagement.namespaceLabels` |
| `deployments.preCreatedNamespaces` | `deployments.namespaceManagement.preCreatedNamespaces` |
| `deployments.taskUsageReport.*` | `deployments.metricsReporting.taskUsageMetrics.*` |
| `deployments.cleanupAirflowDb.*` | `deployments.deploymentLifecycle.cleanupAirflowDb.*` |
| `deployments.deployRollback.*` | `deployments.deploymentLifecycle.deployRollback.*` |
| `deployments.authSideCar.*` | `deployments.authSideCar.*` |
| `deployments.loggingSidecar.*` | `deployments.logging.loggingSidecar.*` |
| `deployments.dagDeploy.*` | `deployments.dagDeploy.*` |
| `deployments.mode` | `deployments.mode` |
| (not previously emitted) | `deployments.logging.enabled` |
| (not previously emitted) | `deployments.logging.provider` |
| (not previously emitted) | `deployments.logging.elasticsearch.*` |
| (not previously emitted) | `deployments.metricsReporting.grafana.enabled` |

### Unchanged paths

The following `global.*` values were **not** moved and remain at their original locations:

- `global.baseDomain`
- `global.privateCaCerts`
- `global.privateRegistry.*`
- `global.customLogging.*`
- `global.extraAnnotations`
- `global.ssl.*`
- `global.nats.*`
- `global.airflowOperator.*`
- `global.istio.*`
- `global.logging.indexNamePrefix`
- `global.logging.provider`
- `global.pgbouncer.*`
- `global.podLabels`
- `global.podAnnotations`
- `global.acme.*`
- `global.helmRepo.*`
- `global.podDisruptionBudgetsEnabled`
- `global.defaultDenyNetworkPolicy`
- `global.tlsSecret`
- `global.enablePerHostIngress`
- `global.airflow.*`
- `global.gitSyncRelay.*`
- `global.manualNamespaceNamesEnabled`
- `global.disableManageClusterScopedResources`
- `global.enableArgoCDAnnotation`
- `global.clusterRoles`
- `global.plane.*`
- `global.storageClass`
- `global.namespaceLabels`

## Example migration

**Before:**

```yaml
global:
  rbacEnabled: true
  sccEnabled: false
  openshiftEnabled: false
  authSidecar:
    enabled: true
    port: 8084
  dagOnlyDeployment:
    enabled: true
  networkPolicy:
    enabled: true
  baseDomain: example.com
```

**After:**

```yaml
global:
  baseDomain: example.com
  rbac:
    enabled: true
  scc:
    enabled: false
  openshift:
    enabled: false
  networkPolicy:
    enabled: true
  authSidecar:
    enabled: true
    port: 8084
  deployMechanisms:
    dagOnlyDeployment:
      enabled: true
```
