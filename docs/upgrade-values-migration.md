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

### Unchanged Keys (No Migration Needed)

These keys already use the correct schema and are not modified:

- `global.networkPolicy.enabled`
- `global.authSidecar.*`
- `global.airflowOperator.*`
- All keys under `astronomer`, `nginx`, `grafana`, `prometheus`,
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

The script only transforms keys that use the old format. If a key already uses
the new format (e.g., `global.rbac.enabled` instead of `global.rbacEnabled`),
it is left untouched.

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

The script uses `ruamel.yaml` in round-trip mode, which preserves inline
comments, block comments, and formatting in most cases. Inline comments on
migrated keys are preserved, and comments on untouched keys are not affected.

### What if my file has keys not listed in the mapping table?

Keys not listed in the mapping table are left completely untouched. The script
only transforms the specific keys it knows about.
