# Adopting bootstrapper-created Secrets before upgrading

## Overview

The Astronomer chart now renders some Secrets as **release-managed manifests**
that older releases created **out of band** via a bootstrapper init container.
The most important example is `<release>-flightdeck-backend`: before the
secrets-from-files change the chart only *consumed* it (via `secretKeyRef`),
while the flightdeck bootstrapper created the live Secret. That live Secret
therefore has no Helm ownership metadata.

Helm 3 refuses to adopt a live resource it did not create, so `helm upgrade`
from a FlightDeck-enabled pre-upgrade release aborts before it changes anything:

```
Error: UPGRADE FAILED: Unable to continue with update: Secret
"astronomer-flightdeck-backend" in namespace "astronomer" exists and cannot be
imported into the current release: invalid ownership metadata; label validation
error: missing key "app.kubernetes.io/managed-by": must be set to "Helm"; ...
```

Helm performs this ownership check in its *prepare* phase — **before** it runs
any pre-upgrade hook — so the conflict cannot be repaired from inside the chart.
The fix is to stamp the required Helm ownership label and annotations onto the
live Secret **before** running `helm upgrade`. The script
`bin/adopt-bootstrap-secrets-pre-upgrade.py` does exactly this.

## When to Use This Guide

Run the adoption step before `helm upgrade` when **all** of the following hold:

- You are upgrading from a chart released **before** secrets-from-files, and
- the release had **FlightDeck enabled** (or data-plane failover on a data
  plane), so the `<release>-flightdeck-backend` Secret already exists.

It is **safe to run before every upgrade**: the script is idempotent and does
nothing on a fresh install, when FlightDeck is disabled, or when the Secret is
already owned by this release. Skipping it when it is not needed costs nothing.

## Prerequisites

- Python 3.10 or later
- `kubectl` configured for the target cluster
- Permission to `get`, `label`, and `annotate` Secrets in the release namespace

## Steps

### 1. Preview (dry run)

```bash
./bin/adopt-bootstrap-secrets-pre-upgrade.py \
  --release-name astronomer --namespace astronomer --dry-run
```

Example output:

```
ADOPT astronomer-flightdeck-backend: stamping Helm ownership metadata for release 'astronomer'
  [dry-run] would run: kubectl --namespace astronomer label secret astronomer-flightdeck-backend --overwrite app.kubernetes.io/managed-by=Helm
  [dry-run] would run: kubectl --namespace astronomer annotate secret astronomer-flightdeck-backend --overwrite meta.helm.sh/release-name=astronomer meta.helm.sh/release-namespace=astronomer

Done. would adopt 1 secret(s); skipped 0.
```

### 2. Adopt

```bash
./bin/adopt-bootstrap-secrets-pre-upgrade.py \
  --release-name astronomer --namespace astronomer
```

### 3. Upgrade

```bash
helm upgrade astronomer . --namespace astronomer -f my-values.yaml
```

## What the script does

For each target Secret (default: `<release>-flightdeck-backend`) it:

1. Skips the Secret if it does not exist (fresh install / FlightDeck disabled).
2. Skips it if it is already owned by this release (idempotent).
3. Otherwise stamps `app.kubernetes.io/managed-by=Helm` plus the
   `meta.helm.sh/release-name` and `meta.helm.sh/release-namespace` annotations,
   so the next `helm upgrade` adopts it. The Secret's data is never read or
   modified — only its metadata is stamped, so the bootstrapped value is
   preserved and the chart's `lookup` helper keeps it byte-identical.

If a Secret is already owned by a **different** Helm release the script refuses
to reassign it and exits non-zero; resolve that conflict deliberately.

### Options

| Flag | Default | Purpose |
| --- | --- | --- |
| `--release-name` | `astronomer` | Helm release name |
| `--namespace` | `astronomer` | Release namespace |
| `--kube-context` | current context | kubectl context to target |
| `--kubectl` | `kubectl` | Path to the kubectl binary |
| `--secret` | known bootstrapper Secrets | Explicit Secret name to adopt (repeatable) |
| `--dry-run` | off | Print actions without modifying anything |

## Note: bundled (non-production) PostgreSQL restarts during the upgrade

secrets-from-files switches the **bundled** PostgreSQL to `POSTGRES_PASSWORD_FILE`,
which changes its StatefulSet pod spec and causes the pod to restart during the
upgrade. Post-upgrade hook Jobs (e.g. `houston-upgrade-deployments`) can briefly
race that restart and fail with `connection refused`; re-running `helm upgrade`
once PostgreSQL is ready completes the upgrade. This affects only the bundled
development PostgreSQL — production deployments use an external database, which
is not restarted by the chart upgrade.
