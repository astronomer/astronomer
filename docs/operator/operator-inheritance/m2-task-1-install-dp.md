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
- **Hard requirement — CP and DP must share the same `baseDomain`.** Houston's cluster registration and downstream URL generation assume the CP's `helm.baseDomain` and the DP's `clusterMetadata.baseDomain` are the same. If the customer's operator cluster terminates traffic at a different domain today, that has to be reconciled before install — either by adopting the CP's baseDomain on the operator cluster, or by introducing a new domain for both. Mixed-baseDomain installs are not supported.

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

### Step 5 — Register the DP with the CP

After the helm install brings up Commander and its public `/metadata` endpoint, the operator cluster has to be registered with the CP so Houston knows about it. This is done by calling Houston's existing `registerCluster` GraphQL mutation — the same path used today for adding a new DP to an APC install.

| Component | Location |
|---|---|
| GraphQL mutation declaration | [`houston-api/src/schema/mutation.js:834-853`](../../../../houston-api/src/schema/mutation.js#L834-L853) |
| Mutation resolver | [`houston-api/src/resolvers/mutation/register-cluster/index.js`](../../../../houston-api/src/resolvers/mutation/register-cluster/index.js) |
| Library function | [`houston-api/src/lib/clusters/index.js:441`](../../../../houston-api/src/lib/clusters/index.js#L441) — `registerCluster()` |
| Metadata fetch | [`houston-api/src/lib/clusters/index.js:852`](../../../../houston-api/src/lib/clusters/index.js#L852) — `fetchClusterMetadata()` GETs `<dataplaneUrl>/metadata` |
| Metadata schema (ajv) | [`houston-api/src/lib/clusters/index.js:775-841`](../../../../houston-api/src/lib/clusters/index.js#L775-L841) — required fields include `baseDomain`, `dataplaneUrl`, `commander.{url,version,airflowChartVersion}`, `releaseName`, `releaseNamespace`, etc. |
| Persisted columns | [`lib/clusters/index.js:376-405`](../../../../houston-api/src/lib/clusters/index.js#L376-L405) — `baseDomain` is one of them, with a `@unique` constraint (P2002 fails with *"A cluster with this base domain already exists"*) |

Required mutation arguments:

```graphql
mutation RegisterDataPlane(
  $name: String!
  $metadataUrl: String!
  $deploymentsConfigOverride: JSON
) {
  registerCluster(
    name: $name
    metadataUrl: $metadataUrl
    deploymentsConfigOverride: $deploymentsConfigOverride
  ) {
    id
    name
    baseDomain
    status
  }
}
```

- `name` — human-readable cluster name (free-form; trimmed).
- `metadataUrl` — public URL of Commander's `/metadata` endpoint on the new DP. Houston `axios.get`s `<metadataUrl>/metadata` (trailing slashes stripped per [`lib/clusters/index.js:856-859`](../../../../houston-api/src/lib/clusters/index.js#L856-L859)).
- `deploymentsConfigOverride` — optional JSON merged into the cluster's `config.deployments` block. Useful for per-cluster overrides (e.g. different runtime versions list); see `mergeConfigs()` call at [`lib/clusters/index.js:465-468`](../../../../houston-api/src/lib/clusters/index.js#L465-L468).

The generator script (Step 3) should print the exact mutation invocation, including the `metadataUrl` it computed from `global.baseDomain` + commander ingress host, so the operator runs one command to register.

> The `baseDomain` returned by Commander's `/metadata` is persisted on the `Cluster` row (`baseDomain` column). Every downstream URL helper — `deploymentsSubdomain()`, `airflowSubdomain()`, `flowerSubdomain()`, `deploymentsUrl()` — reads from `clusterDetails.baseDomain`. See the "Deployment URL handling" section below for what this means when the customer's CRs are reachable at a different URL.

### Step 6 — Post-install verification

- All DP pods Ready.
- Commander gRPC reachable from the **already-running CP** (Houston in the CP cluster can resolve and call Commander in the DP cluster).
- DP registered against the CP — verify the new `Cluster` row exists in Houston and `listClusters` returns it.
- `clusterDetails.baseDomain` matches the CP's `helm.baseDomain` (per the hard prerequisite).
- Existing Airflow CRs untouched (kubectl get airflows -A → identical to pre-install snapshot).
- Existing DAGs still scheduling (sample dag run).
- Prometheus scrape targets include Commander; operator controller-manager metrics either scraped by APC's Prometheus or the customer's.

## Deployment URL handling — adopted CRs

Once an existing `Airflow` CR is adopted (M2 / Task 3), Houston will render that deployment's webserver / flower / airflow URLs using the helpers at [`houston-api/src/lib/utilities/index.js:116-157`](../../../../houston-api/src/lib/utilities/index.js#L116-L157):

```js
// utilities/index.js
export function deploymentsSubdomain({ globalDeploymentsConfig, clusterDetails }) {
  const baseDomain = clusterDetails.baseDomain;                  // line 120 — from Cluster row
  const subdomain  = get(globalDeploymentsConfig, "subdomain");  // line 121
  return `${subdomain}.${baseDomain}`;                            // line 122
}

export function flowerSubdomain({ clusterDetails }) {                // line 129
  return `${clusterDetails.config.dataplane.releaseName}-flower.${clusterDetails.baseDomain}`;
}

export function airflowSubdomain({ clusterDetails }) {               // line 139
  return `${clusterDetails.config.dataplane.releaseName}-airflow.${clusterDetails.baseDomain}`;
}

export function deploymentsUrl({ globalDeploymentsConfig, clusterDetails }) {  // line 149
  return `${scheme()}://${deploymentsSubdomain({ globalDeploymentsConfig, clusterDetails })}`;
}
```

**The problem.** These helpers compute the URL from the cluster's `baseDomain` + the deployment's `releaseName`. For a CR APC just created, those line up — APC's nginx Ingress on the DP routes `<releaseName>-airflow.<baseDomain>` to the right service. For an **adopted** CR the customer's airflow is most likely reachable today at a completely different URL (their own subdomain, possibly a different domain entirely, served by their LB), and APC's nginx has no Ingress rules for it. Result: Houston UI shows a URL the customer can't open.

**The bigger problem — browser auth is scoped to `helm.baseDomain`.** Even if Houston is willing to *render* the customer's URL, the auth cookie that the Airflow webserver needs is set against `helm.baseDomain`, so the browser refuses to send it to a host on a different domain. Two places in the code anchor on this:

- **Houston sets the JWT cookie with `domain = .${helm.baseDomain}`** ([`houston-api/src/lib/jwt/index.js:81-96`](../../../../houston-api/src/lib/jwt/index.js#L81-L96)):

  ```js
  export function setJWTCookie({ response, token }) {
    return response.cookie(getCookieName(), token, {
      domain: `.${config.get("helm.baseDomain")}`,   // <- scoped to leading-dot baseDomain
      path: "/",
      expires: expiresAt,
      secure: ...,
      httpOnly: true
    });
  }
  ```

  And `clearJWTCookie()` at [lines 190-196](../../../../houston-api/src/lib/jwt/index.js#L190-L196) uses the same domain. The browser only sends this cookie to hosts ending in `.${helm.baseDomain}` — anything off-domain is unauthenticated.

- **The UI's OAuth redirect validator rejects off-domain URLs** ([`apc-ui/src/utils/sso.tsx:36-40`](../../../../apc-ui/src/utils/sso.tsx#L36-L40)):

  ```ts
  const dotIndex = appHostname.indexOf('.');
  if (dotIndex === -1) return false;
  const baseDomain = appHostname.substring(dotIndex); // ".astro.acme.com"
  return url.hostname.endsWith(baseDomain);
  ```

  Any post-login redirect to a hostname that doesn't end in the app's root domain is treated as unsafe and discarded.

**Net effect.** The customer's Airflow webserver hostname **must be a subdomain of the CP's `helm.baseDomain` at any depth** (e.g. if `helm.baseDomain = astro.acme.com`, then `airflow-prod.astro.acme.com` and `airflow-prod.eu.astro.acme.com` both work; `airflow.acme.com` does not). Without that, browser auth and OAuth callbacks break — Option B isn't really viable for a customer whose existing URL is on a totally different root domain.

### Decision (per design-review A.5): APC's URL pattern wins; customer keeps their ingress controller

> The earlier draft offered four options (A/B/C/D) for handling the customer's existing URL. **All four were dropped at design review** in favour of a single design grounded in what Houston's auth flow can actually support.

**The decision:** when an adopted deployment is **edited via Houston for the first time**, the SSA patch rewrites the CR's ingress block to APC's standard pattern (`<deployments-subdomain>.<helm.baseDomain>/<releaseName>/airflow`). The customer's previously-published URL stops working at that point.

**What's preserved** is the **ingress controller / load-balancer IP**, not the URL string:

- **Customer using NGINX ingress controller already.** No new ingress controller is installed. APC's helm chart skips bringing up its own. The existing one keeps serving traffic; the only change is the Ingress object's path (now `/<releaseName>/airflow`). Auth annotations are added to the same Ingress.
- **Customer on OpenShift / using a different ingress controller (e.g. OpenShift Routes).** APC's **auth sidecar** mechanism handles auth — set the relevant extra annotation, customer's controller stays in place, no NGINX needed. Load-balancer IP unchanged.

**Why no per-deployment URL override:** the JWT cookie is scoped to `.${helm.baseDomain}` (see code excerpts above). A URL outside that domain cannot work for browser-based auth no matter how Houston renders it. The earlier "Option B / Option D" (per-deployment URL override on the Deployment row) silently broke login for off-domain customers; we explicitly chose not to add that footgun.

**Customer prerequisite:** they must whitelist `*.${helm.baseDomain}` (or the equivalent star-cert / DNS entry). Once that's in place, APC's URL pattern resolves correctly through their existing ingress controller and LB IP.

**Operational impact:**
- Customer needs to update any external links / bookmarks pointing at the old Airflow URL after adoption + first edit.
- No `webserverUrl` field on `AdoptDeploymentInput` (dropped per A.5).
- No `Deployment.config.adoption.urls` block (dropped per A.5).
- No code changes to `deploymentsSubdomain` / `airflowSubdomain` / `deploymentsUrl` (the helpers from Houston's utilities work as-is).

> ~~Old draft: four options A/B/C/D with conditional recommendations.~~ **Replaced by the single design above (A.5).** Options B and D were never viable for off-domain customers anyway (cookie scope). C was a per-CR nginx-proxy workaround that adds operational complexity for a problem A.5 solves directly. A is essentially what we've kept — minus the language about "force migration".

## Affected files (initial estimate)

> Citations are file paths in the local working tree.

| File / area | Change |
|-------------|--------|
| `astronomer/bin/` | New generator script, e.g. `setup-operator-dp.py`. (Naming TBD.) |
| [`astronomer/values.yaml`](../../../values.yaml) | Likely no chart-side changes for this task — only consumed by the generator. |
| [`astronomer/charts/astronomer/templates/houston/houston-configmap.yaml:99-101`](../../../charts/astronomer/templates/houston/houston-configmap.yaml) | Already passes `deployments.mode.operator.enabled` — verify it's correct for DP-only installs. |
| [`astronomer/charts/airflow-operator/values.yaml`](../../../charts/airflow-operator/values.yaml) | Add an `enabled: false` knob so the subchart is skipped when the cluster already has the operator. _(Open question — see below.)_ |
| [`houston-api/src/lib/utilities/index.js:116-157`](../../../../houston-api/src/lib/utilities/index.js#L116-L157) | Extend `deploymentsSubdomain()`, `airflowSubdomain()`, `flowerSubdomain()`, `deploymentsUrl()` to prefer `deployment.config.adoption.urls.*` when present (Option B). |
| `houston-api/src/lib/deployments/` (nginx rule creation, TBD specific file) | Skip Ingress / Service rule emission for deployments where `config.adoption.adopted === true`. |
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
- [ ] **`baseDomain` enforcement.** Houston validates uniqueness of `baseDomain` per cluster ([`lib/clusters/index.js:552-557`](../../../../houston-api/src/lib/clusters/index.js#L552-L557)) but does **not** today validate equality with the CP's `helm.baseDomain`. Should we add an explicit equality check at registration time, or rely on operator runbook discipline?
- [ ] **`registerCluster` from a service account.** The mutation accepts both user and service-account callers ([`lib/clusters/index.js:457-463`](../../../../houston-api/src/lib/clusters/index.js#L457-L463)). What credential should the install script use? Bootstrap a per-DP service account, or require a CP admin token?
- [x] **Deployment URL handling for adopted CRs — resolved at design review (A.5).** APC's URL pattern wins on first edit; customer keeps their ingress controller / LB IP via auth-sidecar or BYO Nginx. No per-deployment URL override. See "Decision (per design-review A.5)" above.
- [ ] **Adopted-deployment URL collection during onboarding.** If we go with Option B/D, where does the customer's per-CR URL come from? The CR itself doesn't carry it explicitly. Inferring from the customer's Ingress / Route resources is possible but fragile. Most likely answer: operator collects it interactively as part of the adopt step (M2 / Task 3).

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
- [ ] CP and DP `baseDomain` equality is enforced (either by the script before install or by Houston at `registerCluster` time).
- [ ] Calling `registerCluster(name, metadataUrl)` from the install runbook successfully creates a `Cluster` row visible to `listClusters`.
- [ ] Houston URL helpers either show the APC-pattern URL (Option A/C) or the customer's existing URL (Option B/D) — per the option chosen for v1 — and no broken-link UI surfaces.
- [ ] Existing Airflow deployments continue to schedule and run DAGs throughout.
- [ ] Documented in a runbook under `astronomer/docs/operator/operator-inheritance/`.
