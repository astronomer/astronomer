# Testing the 1.x to 2.x Upgrade from a Local Chart

This guide walks through upgrading an existing Astronomer 1.x installation to
the unreleased 2.x chart using the local repository checkout. This is useful
for verifying migration scripts and chart changes before an official release.

All commands assume the existing release is in the **`astronomer`** namespace.

## Prerequisites

- `kubectl` access to the target cluster
- `helm` 3.6+
- Python 3.10+ with `ruamel.yaml` installed (`pip install ruamel.yaml`)
- Local checkout of the `astronomer` chart repo on the 2.x branch

## Step 1: Identify the Current Release

```bash
helm ls -n astronomer
```

Note the **RELEASE NAME** (typically `astronomer`) and the **CHART VERSION**
(should be 1.x.x). You will need the release name for all subsequent commands.

```bash
# Example output:
# NAME          NAMESPACE    REVISION  STATUS    CHART                 APP VERSION
# astronomer    astronomer   5         deployed  astronomer-1.1.0      1.1.0
```

## Step 2: Extract the Current Override Values

Pull the user-supplied values (overrides only, not merged defaults) from the
live release:

```bash
helm get values astronomer -n astronomer -o yaml > current-values.yaml
```

Review the file to confirm it contains your customizations:

```bash
cat current-values.yaml
```

## Step 3: Run the Migration Script (Dry Run)

Preview what the migration script will change:

```bash
./bin/migrate-helm-chart-values-1x-to-2x.py --dry-run current-values.yaml
```

If it reports `No migrations needed`, your values are already compatible
and you can skip to Step 5.

## Step 4: Migrate the Values

Run the migration with a backup:

```bash
./bin/migrate-helm-chart-values-1x-to-2x.py --in-place --backup current-values.yaml
```

This creates `current-values.yaml.bak` (original) and modifies
`current-values.yaml` in place with the new schema.

Review the diff between old and new:

```bash
diff current-values.yaml.bak current-values.yaml
```

## Step 5: Build the Local Chart Dependencies

The local chart needs its sub-chart dependencies resolved before it can be
installed:

```bash
cd /path/to/astronomer   # your local repo checkout

helm dep update .
```

If sub-charts are already vendored in `charts/`, you can skip this step.
Verify with:

```bash
ls charts/
```

## Step 6: Dry-Run the Upgrade (Template Rendering)

Before touching the cluster, render the templates locally to check for errors:

```bash
helm template astronomer . \
  -n astronomer \
  -f current-values.yaml \
  --set global.baseDomain=<YOUR_BASE_DOMAIN> \
  > /dev/null
```

If this succeeds with no errors, the chart renders correctly with your migrated
values.

For a more thorough check, use `helm upgrade --dry-run`:

```bash
helm upgrade astronomer . \
  -n astronomer \
  -f current-values.yaml \
  --dry-run
```

This validates against the live cluster state and shows the diff of what would
change.

## Step 7: Perform the Upgrade

```bash
helm upgrade astronomer . \
  -n astronomer \
  -f current-values.yaml \
  --timeout 15m \
  --wait
```

The `--wait` flag blocks until all pods are ready or the timeout is reached.

## Step 8: Verify the Upgrade

### Check release status

```bash
helm ls -n astronomer
```

Confirm the chart version now shows the 2.x version and status is `deployed`.

### Check pod health

```bash
kubectl get pods -n astronomer
```

All pods should be `Running` or `Completed` (for jobs).

### Check Houston receives correct feature flags

```bash
kubectl get configmap -n astronomer -l component=houston -o yaml | grep -A5 "deployments:"
```

Verify the feature flags match what you set in your values file.

### Quick smoke test

```bash
# Verify Houston API is responding
kubectl exec -n astronomer deploy/astronomer-houston -- wget -qO- http://localhost:8871/v1/healthz

# Verify the UI is accessible (if ingress is configured)
curl -s https://app.<YOUR_BASE_DOMAIN>/healthz
```

## Rollback

If something goes wrong, roll back to the previous revision:

```bash
helm rollback astronomer -n astronomer
```

To also revert your values file:

```bash
cp current-values.yaml.bak current-values.yaml
```

## Troubleshooting

### Helm upgrade times out

Increase the timeout and check which pods are failing:

```bash
kubectl get pods -n astronomer --field-selector=status.phase!=Running
kubectl describe pod <failing-pod> -n astronomer
kubectl logs <failing-pod> -n astronomer
```

### Template rendering errors

If `helm template` fails, check the error message for the specific template
and value path. Common issues:

- A value was not migrated (old path still referenced in templates)
- A required value is missing from your override file

Run the migration script again with `--dry-run` to confirm all old paths
were transformed.

### Houston won't start

Check the Houston configmap for malformed YAML:

```bash
kubectl get configmap astronomer-houston-config -n astronomer -o yaml
```

Check Houston logs:

```bash
kubectl logs deploy/astronomer-houston -n astronomer --tail=50
```
