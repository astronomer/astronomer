# M2 / Task 1 — Install the APC data plane onto the operator's cluster

**Parent milestone:** [M2 — Stage 1 → 2 Astro Runtime operator to APC adoption](m2-stage-1-to-2-adoption.md)
**Linear issue:** _not yet filed_
**Owner:** _TBD_
**Effort:** _TBD_

> Linked Linear milestone description (verbatim):
> *"Installing the DP: The kubernetes cluster where operator lives will become an APC dataplane. Install the DP related components there. We need to see what components are used by operator for metrics logging, etc. We need to evaluate how the DP components will be used by operator. For e.g, if operator is using external ES, we have to configure our ES with the external ES. Completion of this would be a script or a process to generate the values.yaml file for the DP."*

---

## Assumptions

This task assumes the following starting state. Any deviation invalidates the design.

- **A working APC control plane already exists in a separate cluster.** Houston, Astro UI, registry, ES, NATS, and the Houston DB are all up, healthy, and reachable from the network the customer's operator cluster lives in. Provisioning the CP is **out of scope** for this task — and out of scope for the entire Operator Inheritance project.
- **The CP is running in `split` mode** (`global.plane.mode: control` per [`astronomer/values.yaml:9-15`](../../../values.yaml#L9-L15)). Unified-mode install onto the operator cluster is **not** considered here.
- **The customer's operator cluster has the Astro Runtime Operator installed**, with one or more `Airflow` CRs already running DAGs.
- **CP ↔ DP network reachability is solved.** Houston's gRPC client can reach Commander's gRPC port over TLS (firewall, VPN, mTLS, etc. are pre-arranged).
- **CP credentials/tokens are available** to mint whatever Commander needs to authenticate back to Houston (registry pull tokens, cross-plane auth header — see `global.authHeaderSecretName` at [`astronomer/values.yaml:7-8`](../../../values.yaml#L7-L8)).

Anything to do with bringing up a fresh CP, or running CP and DP in the same cluster (unified), is **explicitly out of scope** for this task.

## Goal

Take a Kubernetes cluster that already hosts the Astro Runtime Operator (and its Airflow CRs), assume an APC control plane is already running elsewhere, and bring the operator cluster under that CP's management by installing the APC data plane onto it. Deliverable: a documented, repeatable process — at minimum a generator script and a `values.yaml` recipe — that:

1. Installs the DP components onto the operator cluster without disrupting existing Airflow workloads.
2. Registers the new DP with the pre-existing CP (cross-plane auth, registry pull, gRPC reachability).
3. Co-exists with whatever observability the customer already has (their own Prometheus, their own log shipper, their own ES) rather than duplicating it.
4. Leaves the existing operator install in place (no reinstall, no version bump as part of this task — version bump is [M3 / Task B](m3-task-b-upgrade-operator-v16.md)).

## Background — what APC supports today

APC's umbrella chart already supports split CP/DP via `global.plane.mode`, set in [`astronomer/values.yaml:9-15`](../../../values.yaml#L9-L15). Three modes:

| Mode | Components installed |
|------|----------------------|
| `unified` | CP + DP in one cluster/namespace (the APC 0.x behaviour) |
| `control` | CP only (Houston, Astro UI, registry, ES, NATS, …) |
| `data` | DP only (Commander, Prometheus, Vector, Nginx, …) |

The existing local-dev guide [`../../cp-dp-k3d-setup-guide.md`](../../cp-dp-k3d-setup-guide.md) walks through a split install end-to-end using k3d.

### DP-side components (today)

| Component | Subchart / file | Toggle |
|-----------|-----------------|--------|
| Commander | `astronomer/charts/astronomer/` (bundled with the `astronomer/` subchart) | Enabled when `global.plane.mode` ∈ {`data`, `unified`} |
| Prometheus | `astronomer/charts/prometheus/` ([`astronomer/Chart.yaml`](../../../Chart.yaml) dependency, `monitoring` tag) | `global.prometheus.enabled` |
| Vector (log shipper) | `astronomer/charts/vector/` (`logging` tag) | `global.daemonsetLogging.enabled` |
| Nginx (ingress) | `astronomer/charts/nginx/` | `global.nginx.enabled` |
| Pilot (DP-side proxy) | `astronomer/charts/astronomer/templates/pilot/` | `astronomer.pilot.enabled` (default `false`) at [`astronomer/charts/astronomer/values.yaml:724-727`](../../../charts/astronomer/values.yaml#L724-L727) |
| `airflow-operator` subchart | `astronomer/charts/airflow-operator/` | `global.airflowOperator.enabled` at [`values.yaml:52-55`](../../../values.yaml#L52-L55) |

## Background — what the operator brings to the cluster

Per recon of the `airflow-operator/` repo:

- The operator's standalone helm chart at `airflow-operator/helm/` includes only the controller-manager, RBAC, webhook config, and (optionally) cert-manager. It does **not** include Prometheus, Loki/ES, Grafana, or any log shipper.
- The operator imports `monitoringv1` from `github.com/prometheus-operator/prometheus-operator/pkg/apis/monitoring/v1` (see `airflow-operator/main.go:45`) — it can create `ServiceMonitor` CRs if the prom-operator's CRDs are installed.
- Metrics from Airflow itself are emitted via the StatsD CRD (`airflow-operator/apis/airflow/v1beta1/` — `statsd_types.go`, `statsd_webhook_test.go`). StatsD then needs scraping.
- Operator-level runtime config lives at `airflow-operator/config.yaml` and is minimal (`imagePullSecretGenerationEnabled`, `agentTokenIssuer`, `agentTokenJWKS`).

**Implication:** the customer's existing cluster has the operator + its own observability (whatever they brought). When the DP lands, we need to wire the operator's metrics/logs into either APC's stack or the customer's, but not both.

## Proposed approach

### Step 1 — Survey what's already in the cluster

Before installing anything, the generator script inspects the cluster and emits an inventory:

```
- Operator install
  - airflow-operator controller deployment (namespace, image tag, replica count)
  - CRDs present (airflows.airflow.apache.org, ..., expected 14)
  - cert-manager presence
  - prometheus-operator presence (ServiceMonitor CRD)
- Airflow CRs
  - per CR: namespace, name, executor, image, runtimeVersion, scheduler/worker/triggerer replicas, dagDeployment method
- Observability
  - existing Prometheus deployments (any namespace)
  - existing log shippers (vector, fluent-bit, fluentd, filebeat)
  - existing ES / Loki / OpenSearch
  - existing Grafana
- RBAC
  - existing ServiceAccounts / Roles / RoleBindings in each Airflow CR's namespace
- Networking
  - existing NetworkPolicies in each Airflow namespace
  - existing Ingress / Route resources
```

> TODO: choose the implementation. Bash + `kubectl` is portable; a Go binary embedded in `astro-cli` is nicer DX but heavier to ship. _TBD._

### Step 2 — Confirm CP reachability and credentials

Per the assumptions above, the CP already exists. Before installing the DP, the script verifies:

- CP gRPC endpoint is reachable from the operator cluster (probe Houston's external/internal endpoint).
- Cross-plane auth secret material is on hand (the `global.authHeaderSecretName` content, registry pull credentials, any TLS chain the DP needs to trust).
- CP's `baseDomain` and TLS posture are known so the DP values can point at them.

If any of these are missing, abort with a clear error — DP install without CP is not a supported state.

### Step 3 — Generate `values.yaml`

The script generates a DP-only values file (`global.plane.mode: data`) with:

- `global.plane.mode: data` — **not** `unified`. Unified is out of scope per the assumptions.
- `global.baseDomain`, `global.tlsSecret`, `global.privateCaCerts` — collected interactively or from flags; baseDomain should match the CP's view of this DP.
- `global.authHeaderSecretName` and any cross-plane shared-secret material wiring the DP to the existing CP.
- `global.airflowOperator.enabled: true` — but `airflow-operator.enabled: false` at the subchart level, since the operator is already installed. _(See open question below.)_
- Observability toggles, set based on the survey:

| Survey finding | Chart override |
|----------------|----------------|
| Customer runs their own Prometheus | `global.prometheus.enabled: false`; instead point Houston/Commander metrics to the customer Prometheus _(open question — does Houston need our prom?)_ |
| Customer runs their own log shipper | `global.daemonsetLogging.enabled: false`; configure log endpoints to ship via their pipeline _(open question — do we need our ES?)_ |
| Customer has cert-manager | leave APC's cert-manager untouched if version compatible; otherwise `cert-manager.enabled: false` |
| Customer has prom-operator | reuse it for ServiceMonitor scraping of Commander / Airflow CR pods |

- Existing-deployment recognition values: tell Houston/Commander not to take over namespaces it didn't create. _TBD — see [Task 2](m2-task-2-connect-operator-to-commander.md)._

### Step 4 — Install

`helm upgrade --install` the umbrella chart with the generated values. The chart already validates plane mode; CRDs from the operator are not re-applied because the `airflow-operator` subchart is gated off.

### Step 5 — Post-install verification

- All DP pods Ready.
- Commander gRPC reachable from the **already-running CP** (Houston in the CP cluster can resolve and call Commander in the DP cluster).
- DP registered against the CP — verify Houston sees the new DP cluster in its cluster-list.
- Existing Airflow CRs untouched (kubectl get airflows -A → identical to pre-install snapshot).
- Existing DAGs still scheduling (sample dag run).
- Prometheus scrape targets include Commander; operator controller-manager metrics either scraped by APC's Prometheus or the customer's.

## Affected files (initial estimate)

> Citations are file paths in the local working tree.

| File / area | Change |
|-------------|--------|
| `astronomer/bin/` | New generator script, e.g. `setup-operator-dp.py`. (Naming TBD.) |
| [`astronomer/values.yaml`](../../../values.yaml) | Likely no chart-side changes for this task — only consumed by the generator. |
| [`astronomer/charts/astronomer/templates/houston/houston-configmap.yaml:99-101`](../../../charts/astronomer/templates/houston/houston-configmap.yaml) | Already passes `deployments.mode.operator.enabled` — verify it's correct for DP-only installs. |
| [`astronomer/charts/airflow-operator/values.yaml`](../../../charts/airflow-operator/values.yaml) | Add an `enabled: false` knob so the subchart is skipped when the cluster already has the operator. _(Open question — see below.)_ |
| `astronomer/docs/operator/operator-inheritance/` | This folder, plus a user-facing how-to-install runbook (separate doc, _TBD_). |

## Open questions

- [ ] **Re-using customer Prometheus/ES.** APC's Houston and Commander emit metrics and logs themselves — can they be shipped to customer-owned backends, or do we always require our own stack? _(Owner: APC / Observability)_
- [ ] **Operator subchart toggle.** [`astronomer/charts/airflow-operator/`](../../../charts/airflow-operator/) is gated on `global.airflowOperator.enabled`. We need a way to say "enable operator-mode awareness in Houston/Commander, but don't install the operator subchart because the customer already has it." Possible patterns:
  - (a) Two flags: `global.airflowOperator.enabled` (feature gate) + `airflow-operator.enabled` (subchart toggle).
  - (b) Detect existing CRDs at install time and skip subchart install.
  - (c) Always install the subchart and rely on operator-side idempotency.
- [ ] **CRD ownership.** If the operator is already installed, its CRDs are present. Does the `airflow-operator` subchart attempt to re-apply them? See [`astronomer/charts/airflow-operator/values.yaml`](../../../charts/airflow-operator/values.yaml) — `crd.create: false` may already cover this.
- [ ] **cert-manager / webhook certs.** Operator webhooks need TLS certs; APC's cert-manager pattern may conflict with whatever the customer has. _TBD._
- [ ] **Pull-through registry.** Commander pulls Airflow runtime images; if the customer's environment is air-gapped, where does the proxy live? Reuse existing private-CA + proxy config from [`astronomer/values.yaml`](../../../values.yaml#L29-L51)?
- [ ] **Generator output format.** YAML file only, or also a wrapper Helm chart? Whether the generator should be runnable in CI matters for the "managed onboarding" use case.
- [ ] **Idempotency / rerun.** What happens if the script is re-run? Especially relevant if it both inspects and installs.
- [ ] **Failure recovery.** If install partially fails (e.g., nginx hostPort already taken), how do we cleanly roll back without touching the operator's resources?

## Out of scope for this task

- **Provisioning the control plane.** The CP is assumed to already exist (see Assumptions). No CP install steps are covered here.
- **Unified-plane install** onto the operator cluster. Only split-mode DP install is in scope.
- Connecting Commander to existing CRs → [Task 2](m2-task-2-connect-operator-to-commander.md).
- Creating Houston deployment records → [Task 3](m2-task-3-migrate-deployments-to-cp.md).
- Upgrading the operator version → [M3 / Task B](m3-task-b-upgrade-operator-v16.md).
- Reverse migration (DP uninstall while leaving operator alive) → not in M2 scope.

## Acceptance criteria (draft)

- [ ] Script exists at `astronomer/bin/<name>.py` (or equivalent) and runs against a cluster with the operator pre-installed.
- [ ] Script emits a survey artefact + a generated `values.yaml`.
- [ ] `helm upgrade --install` against the generated values brings DP pods to Ready without touching the operator or its CRs.
- [ ] Existing Airflow deployments continue to schedule and run DAGs throughout.
- [ ] Documented in a runbook under `astronomer/docs/operator/operator-inheritance/`.
