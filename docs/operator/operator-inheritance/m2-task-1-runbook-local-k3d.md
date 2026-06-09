# M2 / Task 1 — Runbook: convert a local operator cluster into an APC data plane (k3d)

**Design doc:** [`m2-task-1-install-dp.md`](m2-task-1-install-dp.md)
**Script:** [`astronomer/bin/setup-operator-dp.py`](../../../bin/setup-operator-dp.py)
**Scope:** local k3d dev/POC. Split topology: a **fresh control plane** in its own k3d cluster + the **existing operator cluster** turned into a data plane.

---

## What this does

Takes a Kubernetes cluster that already runs the standalone Astro Runtime Operator (built locally by [`bin/setup-operator-standalone.py`](../../../bin/setup-operator-standalone.py)) and, **without touching the operator install or its `Airflow` CRs**:

1. Stands up a **fresh control plane** (`global.plane.mode: control`) in a new k3d cluster on the **same Docker network** as the operator cluster, so Houston (CP) and Commander (DP) can reach each other.
2. Installs the APC umbrella chart in **`global.plane.mode: data`** onto the existing operator cluster. The `airflow-operator` subchart is **skipped** via `airflow-operator.enabled: false` so APC stays operator-aware (`global.airflowOperator.enabled: true`, giving Commander its `airflow.apache.org` RBAC) *without* reinstalling the operator that's already there — which would otherwise collide on the cluster-scoped `ClusterRole/airflow-operator-manager-role` owned by the existing `airflow-operator-system` release.
3. Prints the **DP→CP registration runbook** — you run `registerCluster` yourself with a SYSTEM_ADMIN token (the script never calls it).

> **Chart dependency:** this relies on the umbrella chart's `airflow-operator` dependency condition `airflow-operator.enabled,global.airflowOperator.enabled` (see [`Chart.yaml`](../../../Chart.yaml)). That toggle lets operator-awareness and subchart-install be set independently and is backward-compatible — when `airflow-operator.enabled` is unset, the dependency is governed by `global.airflowOperator.enabled` exactly as before. This resolves the "operator subchart toggle" open question in [`m2-task-1-install-dp.md`](m2-task-1-install-dp.md).

### Hard safety contract
- Never `helm uninstall`, never (re)apply the `airflow.apache.org` CRDs, never write to the operator namespace, the Airflow CR namespaces, or any `kube-*` namespace.
- The only namespace it creates/writes in each cluster is the APC platform namespace (default `astronomer`).
- It snapshots all `Airflow` CRs before and after install and fails the run if anything changed.

---

## Prerequisites

| Tool | Notes |
|------|-------|
| docker (OrbStack/Docker Desktop) | the operator cluster must already be running |
| k3d v5.x, kubectl, helm 3.12+ | on `PATH` |
| mkcert | `brew install mkcert && mkcert -install` (or `python3 bin/install-ci-tools.py`) |

The operator cluster must already exist. Confirm it first:

```bash
python3 bin/setup-operator-dp.py --survey-only --operator-context k3d-airflow-dev
```

This prints the inventory (operator CRD count, controller namespace/image, cert-manager, existing Prometheus/log-shipper/ES, and every `Airflow` CR) and exits without changing anything.

---

## Run it

For the default local setup (operator cluster `k3d-airflow-dev` on `airflow-standalone-net`, baseDomain `localtest.me`):

```bash
python3 bin/setup-operator-dp.py
```

Useful flags:

```bash
# Different operator cluster / domain:
python3 bin/setup-operator-dp.py --operator-context k3d-airflow-dev --base-domain localtest.me

# Recreate the CP cluster from scratch:
python3 bin/setup-operator-dp.py --recreate-cp-cluster

# Install the DP onto a CP you already brought up (skip CP creation):
python3 bin/setup-operator-dp.py --skip-cp

# Pass extra Helm values to both planes:
python3 bin/setup-operator-dp.py --helm-values /path/to/extra-values.yaml
```

What lands where:

| Cluster | Role | Components |
|---------|------|-----------|
| `k3d-cp01` (new) | control plane | Houston, Astro UI, registry, ES, NATS, nginx, postgres (NodePort 5432) |
| `k3d-airflow-dev` (existing) | data plane | Commander, Prometheus*, Vector*, nginx — **plus** the untouched operator + `Airflow` CRs |

\* Prometheus/Vector are auto-disabled if the survey finds the cluster already runs its own.

---

## Register the DP with the CP (you do this)

The script prints this block at the end with the values filled in. The steps:

1. Add the printed `/etc/hosts` entries so the CP (`houston.localtest.me`, …) and DP (`dp01.localtest.me`, `commander.dp01.localtest.me`, …) hostnames resolve to the k3d serverlb IPs.
2. Verify Commander's metadata endpoint is reachable:
   ```bash
   curl -sk https://<commander-host>/metadata | jq .
   ```
3. Get a SYSTEM_ADMIN token for the CP Houston (local auth is enabled) and call, against `https://houston.localtest.me/v1`:
   ```graphql
   mutation RegisterDataPlane {
     registerCluster(name: "airflow-dev", metadataUrl: "https://<commander-host>") {
       id
       name
       baseDomain
       status
     }
   }
   ```
   The registered `baseDomain` **must equal** the CP's `helm.baseDomain` (`localtest.me`) — the unique-constraint and every downstream URL helper depend on it.

---

## Verify

- Both planes' pods are `Ready`.
- `kubectl --context k3d-airflow-dev get airflows -A` is identical to the pre-install snapshot (the script asserts this).
- `kubectl --context k3d-cp01 -n astronomer get pods` shows Houston/UI/registry up.
- After registration, `listClusters` in Houston returns the new cluster.

---

## Re-run / rollback

- **Idempotent:** safe to re-run; cluster/secret/helm steps converge. CP cluster is recreated only with `--recreate-cp-cluster`.
- **Remove the DP without touching the operator:**
  ```bash
  helm --kube-context k3d-airflow-dev uninstall astronomer -n astronomer
  kubectl --context k3d-airflow-dev delete namespace astronomer
  ```
  This leaves `airflow-operator-system`, the CRDs, cert-manager, and the `Airflow` CRs in place.
- **Tear down the CP:** `k3d cluster delete cp01`.

---

## Troubleshooting

**Install hangs / `helm` stuck in `pending-install`, Prometheus `filesd-reloader` CrashLoopBackOff with `NoSuchTableError: Deployment`/`Cluster`.**
This is a Helm ordering inversion: Houston's DB-migration job (`{release}-houston-db-migrations`, `yarn migrate`) is a `post-install` hook, but the Prometheus `filesd-reloader` sidecar (a main resource) queries the `Cluster`/`Deployment` tables on startup and crashes if they don't exist. Under `helm --wait`, Helm blocks on the crashing pod *before* it runs the `post-install` migration → deadlock. It looks "flaky" because the **first** run is an install (`post-install`, deadlocks) while a **re-run** is an upgrade (`pre-upgrade`, migration runs first → succeeds).

This script avoids it by **not** passing `helm --wait`; Helm still awaits the post-install migration Job (which self-gates on the DB), so the schema is created and the reloader recovers, after which the script waits only on the Deployments registration needs (`_wait_for_deployments_available`, which skips the Prometheus StatefulSet).

If you have a release already stuck in `pending-install` from before this fix, clear it and re-run:
```bash
python3 bin/setup-operator-dp.py --recreate-cp-cluster   # rebuilds cp01 from clean state
# or, to keep the cluster: helm --kube-context k3d-cp01 -n astronomer uninstall astronomer
```

> Proper upstream fix (out of scope here, worth a ticket): make `ap-kuiper-reloader` tolerate a missing table (retry/stay-ready) instead of crashing, or gate the `filesd-reloader` on the schema with an init container.

---

## Out of scope (separate tasks)

- Connecting Commander to the *existing* CRs via server-side apply → [`m2-task-2-connect-operator-to-commander.md`](m2-task-2-connect-operator-to-commander.md).
- Creating Houston `Deployment` records for the CRs (`adoptDeployment`) → [`m2-task-3-migrate-deployments-to-cp.md`](m2-task-3-migrate-deployments-to-cp.md).
- Upgrading the operator → [`m3-task-b-upgrade-operator-v16.md`](m3-task-b-upgrade-operator-v16.md).
