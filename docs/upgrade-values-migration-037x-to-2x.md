# Upgrading values.yaml from Astronomer Chart 0.37.x to 2.x

## Overview

Astronomer chart 2.0 is a major schema upgrade from 0.37.x that includes:

- **Feature flag restructuring**: Scattered `global.*` boolean flags are
  reorganized into domain-grouped structures with a consistent `.enabled`
  pattern (same as the 1.x-to-2.x migration).
- **Removal of obsolete components**: NATS Streaming (stan), Kibana, Fluentd,
  and the Prometheus blackbox exporter are removed.
- **Key renames**: Fluentd is replaced by Vector; PGBouncer configuration keys
  are renamed.
- **Value updates**: PGBouncer port and NATS JetStream defaults are changed.
- **New platform keys**: New keys for control/data plane mode, pod labels,
  cross-plane authentication, and logging provider are added.

A migration script is provided at `bin/migrate-helm-chart-values-037x-to-2x.py`
to automate the transformation.

## Breaking Changes and Warnings

> **Read this section carefully before migrating.** These changes may require
> manual intervention beyond running the migration script.

### NATS Streaming (stan) removed

Chart 2.x removes NATS Streaming entirely and uses **NATS JetStream**
exclusively for internal messaging. The migration script deletes all
stan-related configuration (`global.stan`, `tags.stan`, and the top-level
`stan` section).

**Impact**: In-flight messages in NATS Streaming may be lost during the
upgrade. If your platform relies on message delivery guarantees during the
transition window, drain all stan queues before upgrading.

**Action required**: No configuration action needed — the script handles
deletion. Ensure your platform is in a quiet state before upgrading.

### Fluentd replaced by Vector

Chart 2.x replaces Fluentd with **Vector** for log collection. The migration
script renames the top-level `fluentd` key to `vector`, preserving resource
requests and limits.

**Impact**: Resource values (CPU, memory) carry over. However, **custom Fluentd
configuration** — such as custom pipelines, filters, output plugins, or parser
definitions — does **not** translate to Vector format. If you have customized
Fluentd beyond resource settings, you must manually recreate that configuration
in Vector format.

**Action required**: If you have custom Fluentd configuration, review the
[Vector documentation](https://vector.dev/docs/) and recreate your custom
pipelines before upgrading.

### Kibana removed

Chart 2.x no longer includes Kibana. The migration script deletes the top-level
`kibana` section.

**Impact**: If you use Kibana for log viewing, you will lose that UI after
upgrading. Consider setting up an alternative log viewing solution (such as
Grafana with Loki or direct Elasticsearch queries) before the upgrade.

**Action required**: Plan an alternative log viewing solution if you currently
rely on Kibana.

### Prometheus blackbox exporter removed

Chart 2.x no longer includes the Prometheus blackbox exporter. The migration
script deletes the top-level `prometheus-blackbox-exporter` section.

**Impact**: If you rely on blackbox probing for uptime monitoring of platform
services (Houston, Commander, Registry, Grafana, Elasticsearch, Kibana), that
monitoring will stop after the upgrade.

**Action required**: Set up alternative uptime monitoring before upgrading if
you depend on blackbox exporter probes.

### PGBouncer port changed (5432 → 6543)

The default PGBouncer service port changes from `5432` to `6543`.

**Impact**: If external services or scripts connect to PGBouncer on port 5432,
they will fail to connect after the upgrade.

**Action required**: Update any external services, connection strings, or
scripts that reference the PGBouncer port. If you need to keep port 5432, set
`global.pgbouncer.servicePort: "5432"` in your override file after migration.

### PGBouncer secret key renamed (krb5ConfSecretName → secretName)

The PGBouncer configuration key `global.pgbouncer.krb5ConfSecretName` is
renamed to `global.pgbouncer.secretName`.

**Impact**: The Kubernetes Secret referenced by this key does not change — only
the Helm values key name changes. The migration script handles the rename
automatically.

**Action required**: Verify that the value carried over correctly after
migration. The underlying Kubernetes Secret is unchanged.

### NATS JetStream enabled by default

In 0.37.x, `global.nats.jetStream.enabled` defaults to `false`. In 2.x, it
defaults to `true`. The migration script updates this value.

**Impact**: JetStream requires persistent storage. Ensure your cluster has a
storage class available for JetStream volumes.

**Action required**: Verify that your cluster supports persistent volumes for
NATS JetStream. If you need to keep JetStream disabled, set
`global.nats.jetStream.enabled: false` in your override file after migration.

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
./bin/migrate-helm-chart-values-037x-to-2x.py --dry-run my-values.yaml
```

Example output:

```
Found 28 migration(s) to apply:
  global.rbacEnabled -> global.rbac.enabled: Moved global.rbacEnabled -> global.rbac.enabled
  global.sccEnabled -> global.scc.enabled: Moved global.sccEnabled -> global.scc.enabled
  global.openshiftEnabled -> global.openshift.enabled: Moved global.openshiftEnabled -> global.openshift.enabled
  ...
  global.singleNamespace -> (deleted): Deleted obsolete key global.singleNamespace
  global.veleroEnabled -> (deleted): Deleted obsolete key global.veleroEnabled
  ...
  fluentd -> vector: Renamed fluentd -> vector
  global.pgbouncer.krb5ConfSecretName -> global.pgbouncer.secretName: Renamed ...
  global.pgbouncer.servicePort -> global.pgbouncer.servicePort: Updated ... "5432" -> "6543"
  ...
  (new) -> global.plane: Added global.plane with default value
  ...
```

If you see `No migrations needed`, your file is already compatible.

### 3. Run the Migration

**Option A: In-place with backup (recommended)**

```bash
./bin/migrate-helm-chart-values-037x-to-2x.py --in-place --backup my-values.yaml
```

This modifies your file directly and creates `my-values.yaml.bak` as a backup.

**Option B: Write to a new file**

```bash
./bin/migrate-helm-chart-values-037x-to-2x.py my-values.yaml migrated-values.yaml
```

**Option C: Output to stdout (for review or piping)**

```bash
./bin/migrate-helm-chart-values-037x-to-2x.py my-values.yaml > migrated-values.yaml
```

### 4. Review the Migrated File

Open the migrated file and verify the changes look correct. Pay special
attention to:

- **New default values** — review the [New Keys Added with
  Defaults](#new-keys-added-with-defaults) table below and override any
  defaults that do not match your environment.
- **Fluentd-to-Vector rename** — if you had custom Fluentd configuration, only
  the resource values carry over.
- **PGBouncer port** — confirm the new port (6543) works for your setup, or
  override it back to 5432.

### 5. Upgrade the Chart

```bash
helm upgrade <release-name> astronomer/astronomer \
  --version 2.x.x \
  -f migrated-values.yaml \
  --namespace <namespace>
```

## Complete Migration Mapping

### Restructured Keys

These keys are reorganized from flat flags into nested domain-grouped
structures:

| Old Path (0.37.x) | New Path (2.x) | Type |
|---|---|---|
| `global.rbacEnabled` | `global.rbac.enabled` | boolean → nested |
| `global.sccEnabled` | `global.scc.enabled` | boolean → nested |
| `global.openshiftEnabled` | `global.openshift.enabled` | boolean → nested |
| `global.networkNSLabels` | `global.networkNSLabels.enabled` | boolean → nested |
| `global.namespaceFreeFormEntry` | `global.namespaceManagement.namespaceFreeFormEntry.enabled` | boolean → nested |
| `global.taskUsageMetricsEnabled` | `global.metricsReporting.taskUsageMetrics.enabled` | boolean → nested |
| `global.deployRollbackEnabled` | `global.deploymentLifecycle.deployRollback.enabled` | boolean → nested |
| `global.features.namespacePools.*` | `global.namespaceManagement.namespacePools.*` | subtree move |
| `global.dagOnlyDeployment.*` | `global.deployMechanisms.dagOnlyDeployment.*` | subtree move |
| `global.loggingSidecar.*` | `global.logging.loggingSidecar.*` | subtree move |

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

### Deleted Keys

These keys are removed because the underlying features have been removed or
replaced:

| Deleted Key | Reason |
|---|---|
| `global.singleNamespace` | Single-namespace mode no longer supported |
| `global.veleroEnabled` | Velero integration removed from chart |
| `global.enableHoustonInternalAuthorization` | Internal authorization mechanism replaced |
| `global.nodeExporterSccEnabled` | Node exporter SCC no longer needed |
| `global.stan` | NATS Streaming replaced by NATS JetStream |
| `tags.stan` | NATS Streaming tag removed |
| `stan` (top-level) | NATS Streaming deployment removed |
| `kibana` (top-level) | Kibana replaced; see [Breaking Changes](#kibana-removed) |
| `prometheus-blackbox-exporter` (top-level) | Blackbox exporter removed; see [Breaking Changes](#prometheus-blackbox-exporter-removed) |

### Renamed Keys

| Old Key | New Key | Notes |
|---|---|---|
| `fluentd` (top-level) | `vector` (top-level) | Subtree preserved (resource values carry over). Custom Fluentd config requires manual recreation. |
| `global.pgbouncer.krb5ConfSecretName` | `global.pgbouncer.secretName` | The referenced Kubernetes Secret is unchanged. |

### Value Updates

| Key Path | Old Value (0.37.x) | New Value (2.x) | Reason |
|---|---|---|---|
| `global.pgbouncer.servicePort` | `"5432"` | `"6543"` | Avoids conflict with PostgreSQL default port. Override back to `"5432"` if needed. |
| `global.nats.jetStream.enabled` | `false` | `true` | JetStream replaces NATS Streaming. Override to `false` only if not using JetStream. |

### New Keys Added with Defaults

The migration script adds these keys with default values if they are not already
present. **Review each key and override the default if it does not match your
environment.**

| Key Path | Default Value | Description | Action Needed? |
|---|---|---|---|
| `global.authHeaderSecretName` | `~` (null) | Name of Kubernetes secret for cross-plane authentication (registry, federation). | Set this if running in multi-plane (control + data) mode. Not needed for unified mode. |
| `global.plane.mode` | `"unified"` | Platform operating mode: `control`, `data`, or `unified`. | Change to `control` or `data` if running a multi-plane deployment. |
| `global.plane.domainPrefix` | `""` | Cluster identifier prefix for multi-plane DNS. | Set to your cluster ID if running in multi-plane mode. |
| `global.podLabels` | `{}` | Labels applied to every pod. | Add labels if you need them for monitoring, cost allocation, or policy enforcement. |
| `global.logging.provider` | `~` (null) | Logging provider identifier. | Set if using a specific logging backend. |
| `nats.init.resources.requests.cpu` | `"75m"` | NATS init container CPU request. | Override if your cluster needs different resource settings. |
| `nats.init.resources.requests.memory` | `"30Mi"` | NATS init container memory request. | Override if your cluster needs different resource settings. |
| `nats.init.resources.limits.cpu` | `"250m"` | NATS init container CPU limit. | Override if your cluster needs different resource settings. |
| `nats.init.resources.limits.memory` | `"100Mi"` | NATS init container memory limit. | Override if your cluster needs different resource settings. |

### Unchanged Keys (No Migration Needed)

These keys already use the correct schema and are not modified:

- `global.networkPolicy.enabled`
- `global.authSidecar.*`
- `global.airflowOperator.*`
- `global.nats.enabled`, `global.nats.replicas`
- `global.customLogging.*`
- `global.privateCaCerts`, `global.privateCaCertsAddToHost.*`
- `global.ssl.*`
- `global.azure.*`
- `global.platformNodePool.*`
- `global.privateRegistry.*`
- `global.airflow.*`
- `global.gitSyncRelay.*`
- Most keys under `astronomer` **outside** `astronomer.houston.config`
- All keys under `nginx`, `grafana`, `prometheus`,
  `elasticsearch`, `kube-state`, `nats` (except init resources)

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

3. To downgrade the chart after a Helm upgrade:
   ```bash
   helm rollback <release-name> <previous-revision> --namespace <namespace>
   ```

## FAQ

### What if I only override a few values?

The script handles partial override files. It will only migrate the old keys
that are present in your file. Keys you haven't overridden are inherited from
the chart defaults and do not need to be in your file. The `AddKeyIfMissing`
rules will add new keys (like `global.plane`) with safe defaults, which you can
remove if you prefer to rely on chart defaults.

### What if I have both old and new keys?

If a key already exists at the new-schema path, the new-schema value takes
precedence and the stale old key is removed. For example, if your file contains
both `global.rbacEnabled: true` and `global.rbac.enabled: false`, the script
keeps `global.rbac.enabled: false` and deletes `global.rbacEnabled`.

The same precedence applies to renames: if both `fluentd` and `vector` exist
at the top level, the `vector` subtree is preserved and `fluentd` is deleted.

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
  comments transfer to the new leaf key.
- **Moved subtrees** (e.g., `dagOnlyDeployment` →
  `deployMechanisms.dagOnlyDeployment`): All comments within the subtree are
  preserved.
- **Renamed keys** (e.g., `fluentd` → `vector`): Inline comments on the
  renamed key transfer to the new key name.
- **Deleted keys**: Comments on deleted keys are removed with the key.

### What if my file has keys not listed in the mapping table?

Keys not listed in the mapping table are left completely untouched. The script
only transforms the specific keys it knows about.

### I have custom Fluentd configuration. What do I do?

The migration script only renames the `fluentd` key to `vector` and preserves
the subtree (including resource settings). Any Fluentd-specific configuration
(custom pipelines, filters, output plugins) will not work with Vector.

Before upgrading:

1. Document your current Fluentd customizations.
2. Recreate them in Vector format using the
   [Vector documentation](https://vector.dev/docs/).
3. Update the `vector` section in your migrated values file with the new
   Vector-compatible configuration.

### What if I was using the old PGBouncer port (5432)?

If you need to keep the old port, add this to your migrated values file:

```yaml
global:
  pgbouncer:
    servicePort: "5432"
```

This overrides the script's update to `6543`.

### How does this differ from the 1.x-to-2.x migration?

The 0.37.x-to-2.x migration is a superset of the 1.x-to-2.x migration. It
includes all 10 feature flag restructuring rules from the 1.x migration, plus
18 additional rules for:

- Deleting 9 obsolete keys
- Renaming 2 keys (fluentd → vector, pgbouncer secret name)
- Updating 2 values (pgbouncer port, JetStream enabled)
- Adding 5 new keys with defaults

If you are already on 1.x, use `bin/migrate-helm-chart-values-1x-to-2x.py`
instead, as it is a smaller and more targeted migration.
