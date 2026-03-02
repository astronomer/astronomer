# Feature flag configuration path migration

This document maps every relocated Helm value from the previous scattered layout to the new unified `global.features.*` structure. Use it when upgrading custom `values.yaml` overrides to the current chart version.

## Why this changed

Feature flags were previously spread across the root of `global` with inconsistent naming (boolean suffixes like `rbacEnabled`, nested objects like `authSidecar`, standalone booleans like `namespaceFreeFormEntry`). They are now consolidated under `global.features.*` with a consistent `enabled` boolean pattern.

## Migration table

### Simple boolean flags

| Old path | New path |
|---|---|
| `global.rbacEnabled` | `global.features.rbac.enabled` |
| `global.sccEnabled` | `global.features.scc.enabled` |
| `global.openshiftEnabled` | `global.features.openshift.enabled` |
| `global.networkPolicy.enabled` | `global.features.networkPolicy.enabled` |
| `global.networkNSLabels` | `global.features.networkNSLabels.enabled` |
| `global.namespaceFreeFormEntry` | `global.features.namespaceFreeFormEntry` |
| `global.taskUsageMetricsEnabled` | `global.features.taskUsageMetrics.enabled` |
| `global.deployRollbackEnabled` | `global.features.deployRollback.enabled` |

### Complex configuration blocks

These blocks moved in their entirety. All nested keys remain the same.

| Old path | New path |
|---|---|
| `global.dagOnlyDeployment.*` | `global.features.dagOnlyDeployment.*` |
| `global.loggingSidecar.*` | `global.features.loggingSidecar.*` |
| `global.authSidecar.*` | `global.features.authSidecar.*` |

### Houston configmap output changes

The rendered Houston configuration (`production.yaml` inside the Houston ConfigMap) also changed. If you parse or assert against its structure:

| Old output path | New output path |
|---|---|
| `deployments.dagOnlyDeployment` (boolean) | `deployments.features.dagOnlyDeployment.enabled` |
| `deployments.namespaceFreeFormEntry` (boolean) | `deployments.features.namespaceFreeFormEntry.enabled` |
| `deployments.hardDeleteDeployment` (boolean) | `deployments.features.hardDeleteDeployment.enabled` |
| `deployments.taskUsageReport.*` | `deployments.features.taskUsageMetrics.*` |
| `deployments.cleanupAirflowDb.*` | `deployments.features.cleanupAirflowDb.*` |
| `deployments.deployRollback.*` | `deployments.features.deployRollback.*` |
| `deployments.authSideCar.*` | `deployments.features.authSideCar.*` |
| `deployments.loggingSidecar.*` | `deployments.features.loggingSidecar.*` |
| `deployments.dagDeploy.*` | `deployments.features.dagDeploy.*` |
| `deployments.mode` | `deployments.features.mode` |
| `deployments.manualNamespaceNames` (boolean) | `deployments.features.manualNamespaceNames` |

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
- `global.logging.*`
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
  features:
    rbac:
      enabled: true
    scc:
      enabled: false
    openshift:
      enabled: false
    authSidecar:
      enabled: true
      port: 8084
    dagOnlyDeployment:
      enabled: true
    networkPolicy:
      enabled: true
```
