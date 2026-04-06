# Upgrading values.yaml from Astronomer Chart 1.x to 2.x

## Overview

Astronomer chart 2.0 introduces a unified feature flag schema that reorganizes
scattered `global.*` boolean flags into domain-grouped structures with a
consistent `.enabled` pattern. This guide walks you through migrating your
existing `values.yaml` override file to the new schema.

A migration script is provided at `bin/migrate-helm-chart-values-1x-to-2x.py`
to automate the transformation.

## When to Use This Guide

Use this guide when upgrading from Astronomer Helm chart **1.x** to **2.x**.
If you have a custom `values.yaml` file that you pass to `helm upgrade` via
the `-f` flag, you must migrate it before upgrading.

## Prerequisites

- Python 3.10 or later
- `ruamel.yaml` Python package:
  ```bash
  pip install ruamel.yaml
  ```

## Migration Steps

### 1. Back Up Your Current Override File

```bash
cp my-values.yaml my-values.yaml.backup
```

### 2. Preview Changes (Dry Run)

Run the migration script in dry-run mode to see what will change without
modifying any files:

```bash
./bin/migrate-helm-chart-values-1x-to-2x.py --dry-run my-values.yaml
```

Example output:

```
Found 10 migration(s) to apply:
  global.rbacEnabled -> global.rbac.enabled
  global.sccEnabled -> global.scc.enabled
  global.openshiftEnabled -> global.openshift.enabled
  global.networkNSLabels -> global.networkNSLabels.enabled
  global.namespaceFreeFormEntry -> global.namespaceManagement.namespaceFreeFormEntry.enabled
  global.taskUsageMetricsEnabled -> global.metricsReporting.taskUsageMetrics.enabled
  global.deployRollbackEnabled -> global.deploymentLifecycle.deployRollback.enabled
  global.features.namespacePools -> global.namespaceManagement.namespacePools
  global.dagOnlyDeployment -> global.deployMechanisms.dagOnlyDeployment
  global.loggingSidecar -> global.logging.loggingSidecar
```

If you see `No migrations needed`, your file is already compatible.

### 3. Run the Migration

**Option A: In-place with backup (recommended)**

```bash
./bin/migrate-helm-chart-values-1x-to-2x.py --in-place --backup my-values.yaml
```

This modifies your file directly and creates `my-values.yaml.bak` as a backup.

**Option B: Write to a new file**

```bash
./bin/migrate-helm-chart-values-1x-to-2x.py my-values.yaml migrated-values.yaml
```

**Option C: Output to stdout (for review or piping)**

```bash
./bin/migrate-helm-chart-values-1x-to-2x.py my-values.yaml > migrated-values.yaml
```

### 4. Review the Migrated File

Open the migrated file and verify the changes look correct. The script
preserves YAML comments and formatting.

### 5. Upgrade the Chart

```bash
helm upgrade <release-name> astronomer/astronomer \
  --version 2.x.x \
  -f migrated-values.yaml \
  --namespace <namespace>
```

## Complete Migration Mapping

| Old Path (1.x) | New Path (2.x) | Type |
|---|---|---|
| `global.rbacEnabled` | `global.rbac.enabled` | boolean -> nested |
| `global.sccEnabled` | `global.scc.enabled` | boolean -> nested |
| `global.openshiftEnabled` | `global.openshift.enabled` | boolean -> nested |
| `global.networkNSLabels` | `global.networkNSLabels.enabled` | boolean -> nested |
| `global.namespaceFreeFormEntry` | `global.namespaceManagement.namespaceFreeFormEntry.enabled` | boolean -> nested |
| `global.taskUsageMetricsEnabled` | `global.metricsReporting.taskUsageMetrics.enabled` | boolean -> nested |
| `global.deployRollbackEnabled` | `global.deploymentLifecycle.deployRollback.enabled` | boolean -> nested |
| `global.features.namespacePools.*` | `global.namespaceManagement.namespacePools.*` | subtree move |
| `global.dagOnlyDeployment.*` | `global.deployMechanisms.dagOnlyDeployment.*` | subtree move |
| `global.loggingSidecar.*` | `global.logging.loggingSidecar.*` | subtree move |

The script also migrates flat boolean flags under
`astronomer.houston.config.deployments` to nested `.enabled` paths (for example
`dagProcessorEnabled` → `airflowComponents.dagProcessor.enabled`), moves a few
non-boolean keys to grouped sections, and deletes obsolete deployment config
keys.

Additionally, Houston config passthrough keys under `astronomer.houston.config`
are migrated to match Houston's new nested `.enabled` schema. Common examples
include `emailConfirmation` → `emailConfirmation.enabled` and
`publicSignups` → `publicSignups.enabled`. Nested sub-section keys like
`auth.openidConnect.idpGroupsImportEnabled` →
`auth.openidConnect.idpGroupsImport.enabled` are also handled.

Run `./bin/migrate-helm-chart-values-1x-to-2x.py --dry-run your-values.yaml`
to see the exact list for your file.

### Houston Config Passthrough Keys

If your values file overrides Houston application config via
`astronomer.houston.config`, these flat boolean flags are migrated to the
new nested `.enabled` pattern that Houston 2.x expects:

| Old Path (under `houston.config`) | New Path | Type |
|---|---|---|
| `emailConfirmation` (boolean) | `emailConfirmation.enabled` | boolean → nested |
| `publicSignups` (boolean) | `publicSignups.enabled` | boolean → nested |
| `updateRuntimeCheckEnabled` | `updateRuntimeCheck.enabled` | boolean → nested |
| `updateAirflowCheckEnabled` | `updateAirflowCheck.enabled` | boolean → nested |
| `subdomainHttpsEnabled` | `subdomainHttps.enabled` | boolean → nested |
| `disableSSLVerify` | `sslVerification.enabled` | boolean → nested (inverted) |
| `useAutoCompleteForSensitiveFields` | `autoCompleteForSensitiveFields.enabled` | boolean → nested |
| `shouldLogUsername` | `logUsername.enabled` | boolean → nested |
| `auth.openidConnect.idpGroupsImportEnabled` | `auth.openidConnect.idpGroupsImport.enabled` | boolean → nested |
| `auth.openidConnect.idpGroupsRefreshEnabled` | `auth.openidConnect.idpGroupsRefresh.enabled` | boolean → nested |
| `auth.openidConnect.insecureIDPTokenLog` | `auth.openidConnect.insecureIDPTokenLog.enabled` | boolean → nested |
| `webserver.graphqlPlaygroundEnabled` | `webserver.graphqlPlayground.enabled` | boolean → nested |
| `nats.tlsEnabled` | `nats.tls.enabled` | boolean → nested |
| `apollo.auditMiddlewareEnabled` | `apollo.auditMiddleware.enabled` | boolean → nested |
| `workers.dplink.debugEnabled` | `workers.dplink.debug.enabled` | boolean → nested |
| `deployments.mockWebhook.krbEnabled` | `deployments.mockWebhook.krb.enabled` | boolean → nested |
| `deployments.mockWebhook.krbRealm` | `deployments.mockWebhook.krb.realm` | key move |

### Unchanged Keys (No Migration Needed)

These keys already use the correct schema and are not modified:

- `global.networkPolicy.enabled`
- `global.authSidecar.*`
- `global.airflowOperator.*`
- Most keys under `astronomer` **outside** `astronomer.houston.config`
- All keys under `nginx`, `grafana`, `prometheus`,
  `elasticsearch`, `vector`, `kube-state`, `nats`, `tags`

## Rollback

If you need to revert after migration:

1. If you used `--backup`, restore from the `.bak` file:
   ```bash
   cp my-values.yaml.bak my-values.yaml
   ```

2. If you used `--in-place` without `--backup`, restore from your manual backup:
   ```bash
   cp my-values.yaml.backup my-values.yaml
   ```

## FAQ

### What if I only override a few values?

The script handles partial override files. It will only migrate the old keys
that are present in your file. Keys you haven't overridden are inherited from
the chart defaults and do not need to be in your file.

### What if I have both old and new keys?

If a key already exists at the new-schema path, the new-schema value takes
precedence and the stale old key is removed. For example, if your file contains
both `global.rbacEnabled: true` and `global.rbac.enabled: false`, the script
keeps `global.rbac.enabled: false` and deletes `global.rbacEnabled`. The same
precedence applies to subtree moves: if both `global.dagOnlyDeployment` and
`global.deployMechanisms.dagOnlyDeployment` exist, the new-location subtree is
preserved and the old-location subtree is deleted.

### What if I have a full copy of values.yaml instead of just overrides?

The script works on full files too, but we recommend extracting only your
customizations into a separate override file. Running the migration on a full
copy of the old defaults will migrate the feature flags but may also carry
forward old default values (like image tags) that should be updated to the
new chart defaults.

### Is the migration idempotent?

Yes. Running the script multiple times on the same file produces the same
output. Running it on an already-migrated file reports "No migrations needed"
and makes no changes.

### What about YAML comments?

The script uses `ruamel.yaml` in round-trip mode, which preserves comments and
formatting. Specifically:

- **Untouched keys**: All comments (inline, block, and end-of-line) are
  unaffected.
- **Renamed boolean keys** (e.g., `rbacEnabled` → `rbac.enabled`): Inline
  comments transfer to the new leaf key. Block comments above the old key
  remain in place and reattach to the next sibling key.
- **Moved subtrees** (e.g., `dagOnlyDeployment` → `deployMechanisms.dagOnlyDeployment`):
  All comments within the subtree are preserved, including inline comments on
  the subtree root key.

### What if my file has keys not listed in the mapping table?

Keys not listed in the mapping table are left completely untouched. The script
only transforms the specific keys it knows about.
