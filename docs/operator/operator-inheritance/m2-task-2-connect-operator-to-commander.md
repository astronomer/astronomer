# M2 / Task 2 — Connect existing operator CRDs to Commander

**Parent milestone:** [M2 — Stage 1 → 2 Astro Runtime operator to APC adoption](m2-stage-1-to-2-adoption.md)
**Linear issue:** _not yet filed_
**Owner:** _TBD_
**Effort:** _TBD_

> Linked Linear milestone description (verbatim):
> *"Connect the already installed operator specs to commander: Commander should be able to send spec changes to Operator specs (Airflow deployment specs) and operator should be able to reconcile."*

---

## Goal

When the customer's cluster already has `Airflow` custom resources running (created by the Astro Runtime Operator before APC arrived), Commander must be able to:

1. Discover those CRs.
2. Update them — apply spec changes that flow from Houston without recreating, deleting, or stomping the existing pods.
3. Delete them, if Houston's deployment-deleted worker fires.
4. Coexist with the operator's reconcile loop — i.e. not race the operator's controller into an inconsistent state.

## Background — current behaviour

### Commander's `ApplyCustomResource` is blind create-or-update

Based on recon:

- Proto: [`commander/_proto/custom_resource.proto:9-25`](../../../../commander/_proto/custom_resource.proto#L9-L25) — `ApplyCustomResourceRequest` carries `spec` (string JSON), `namespace`, `apiVersion`, `kind`, `name`, `secrets`, `configMaps`, `k8sManifests`, `dagDeploymentType`, namespace labels/annotations. **No fields for owner-references, adoption mode, or "leave existing spec fields alone".**
- Handler: [`commander/api/custom_resource.go:10-17`](../../../../commander/api/custom_resource.go#L10-L17) — thin pass-through to `provisioner.ApplyCustomResource(in)`.
- Implementation: [`commander/kubernetes/custom_resource.go:18-49`](../../../../commander/kubernetes/custom_resource.go#L18-L49) — pseudo-flow:
  1. Build an unstructured object from the request `spec`.
  2. GET the existing object.
  3. If `IsNotFound` → `Create()`.
  4. Else → set `resourceVersion` from the live object and `Update()` it. **This replaces the entire `.spec` of the CR.**

**Consequence:** if a customer's `Airflow` CR has fields Houston didn't populate (e.g. customer-set tolerations, custom env vars, a sidecar via patches, a non-Astronomer image registry), the very first `ApplyCustomResource` call wipes them.

### Houston's spec generation is monolithic

- [`houston-api/src/lib/deployments/operator/index.js:728`](../../../../houston-api/src/lib/deployments/operator/index.js#L728) — `getCRDSpecFromHelmValues()` constructs a full Airflow CR spec from helm values + the deployment record.
- [`houston-api/src/lib/deployments/operator/index.js:1362`](../../../../houston-api/src/lib/deployments/operator/index.js#L1362) — `createOrUpdateDeploymentForOperatorMode()` packages the spec + secrets + configmaps and calls `commander.request(..., "ApplyCustomResource", …)` (see lines 1437–1462).
- Workers that invoke this:
  - [`houston-api/src/workers/deployment-upserted-for-create/index.js:281`](../../../../houston-api/src/workers/deployment-upserted-for-create/index.js#L281)
  - [`houston-api/src/workers/deployment-upserted-for-update/index.js:22`](../../../../houston-api/src/workers/deployment-upserted-for-update/index.js#L22)

There is **no read-back / merge step** — Houston is authoritative, the spec is end-to-end regenerated, Commander applies it.

### Operator-side knobs we can lean on

In `airflow-operator/`:

- `airflow-operator/controllers/airflow/airflow_controller.go` has an `isReconciliationPaused()` check around lines 365–414 that honours a `constants.AirflowReconciliationPausedUntilAnnotation` annotation. If set, the controller logs *"Reconciliation paused via annotation, skipping"* and returns early.
- `airflow-operator/apis/airflow/v1beta1/airflow_types.go` includes `LocalSettings.ExternallyManaged` (around line 117) and `UseExternallyManagedFernetKey` (around line 659). These signal that specific bits are externally managed and the controller will skip their creation (e.g., the controller skips Fernet secret creation at airflow_controller.go:1007 when this is set).

Neither flag is currently set by Houston when generating CRD spec.

## Problem statement (concrete)

Given:

- Cluster contains `Airflow` CR `acme-airflow` in namespace `acme-prod`, spec authored by the customer.
- APC arrives; Houston is given a deployment record for `acme-airflow` (Task 3) and the create-worker fires.
- Today's flow: worker → `createOrUpdateDeploymentForOperatorMode()` → `commander.ApplyCustomResource(spec=NEW_SPEC)` → `Update()` overwrites `.spec`.

We need to change this so the existing spec is **the baseline** and only deltas explicitly intended by Houston are pushed.

## Proposed approach

There are three viable shapes. They're not mutually exclusive — a real implementation may combine 2 and 3.

### Option A — Server-side apply with field ownership

Switch Commander's `ApplyCustomResource` path from `Create` / `Update` to **server-side apply** with a stable field-manager name (e.g. `apc-commander`). Houston declares only the fields APC cares about; everything else stays owned by whoever set it (operator, kubectl, customer).

Pros:
- Native Kubernetes pattern (`kubectl apply --server-side`).
- Per-field ownership tracking is built in.
- No bespoke merge code in Commander.

Cons:
- Houston's `getCRDSpecFromHelmValues()` currently emits a *complete* spec; we'd need to slim it to only the fields APC owns, or use force-ownership tags carefully.
- Conflicts (when the customer also edits the same field) surface as 409 — needs explicit handling.

Affected files:
- [`commander/kubernetes/custom_resource.go`](../../../../commander/kubernetes/custom_resource.go) — replace `Update()` with `Patch(types.ApplyPatchType, …, FieldManager: "apc-commander", Force: false/true)`.
- [`houston-api/src/lib/deployments/operator/index.js`](../../../../houston-api/src/lib/deployments/operator/index.js) — emit a partial spec or annotate fields with `x-kubernetes-list-type` for proper merge semantics.
- Proto: add `field_manager` and `force_apply` to [`commander/_proto/custom_resource.proto`](../../../../commander/_proto/custom_resource.proto).

### Option B — "Adopted" flag in the deployment record

Mark a deployment as "adopted" in Houston (Task 3 sets the flag). When the flag is on, Commander either skips the apply call entirely, or applies a narrowed-down spec. Operator continues to reconcile as before — APC just stops fighting it.

Pros:
- Smallest blast radius.
- Backwards compatible — non-adopted deployments behave exactly as today.

Cons:
- "Adopted forever" — adopted deployments don't benefit from APC's spec updates (image bumps, config changes from UI). Need a separate path to "promote to full management."
- Need consistent enforcement at every call site (create, update, image-update, env-update, delete).

Affected files:
- [`houston-api/prisma/schema.prisma`](../../../../houston-api/prisma/schema.prisma) — new field on `Deployment` (could live inside the existing `config` JSONB column to avoid migration — see Task 3).
- [`houston-api/src/workers/deployment-upserted-for-create/index.js`](../../../../houston-api/src/workers/deployment-upserted-for-create/index.js) — branch on adopted flag.
- [`houston-api/src/workers/deployment-upserted-for-update/index.js`](../../../../houston-api/src/workers/deployment-upserted-for-update/index.js) — same.
- [`houston-api/src/workers/deployment-image-update/index.js`](../../../../houston-api/src/workers/deployment-image-update/) — same.
- [`houston-api/src/workers/deployment-variables-updated/index.js`](../../../../houston-api/src/workers/deployment-variables-updated/) — same.
- [`houston-api/src/workers/deployment-deleted/index.js`](../../../../houston-api/src/workers/deployment-deleted/) — for delete, do we cascade to the CR? See open questions.

### Option C — Reconciliation handoff via operator annotation

Use the operator's existing `AirflowReconciliationPausedUntilAnnotation` to pause the operator's controller for the duration of a Commander update; Commander applies; un-pause. Or, conversely, **APC sets the annotation indefinitely** to declare "APC is now authoritative; operator, don't touch this CR" — but that breaks reconciliation entirely and loses the point of having an operator.

Pros:
- Reuses existing operator support.

Cons:
- Not really adoption — it's takeover.
- Pause-then-apply-then-unpause races are subtle.

Likely **not** the primary design — kept here for completeness.

### Recommendation

Combine **A + B**:
- B (adoption flag) lets us ship safely without touching every existing customer.
- A (server-side apply) is the longer-term direction even for non-adopted deployments — it makes Commander's behaviour predictable and avoids the silent stomp.

### Emergency rollback — install-wide freeze

If A or B misbehave in the field, we need a way to stop APC from touching adopted CRs without rolling back the whole deployment. The lever: a new Houston env flag `OPERATOR_INHERITANCE_FREEZE_EDITS` (default `false`). When `true`, every worker that calls Commander checks `deployment.config.adoption.adopted` first and short-circuits — no `ApplyCustomResource`, no `DeleteCustomResource`. The CR keeps running, reconciled by the operator alone, until we fix the bug and flip the flag back.

Implementation lives in the workers, not Commander — Commander stays a dumb pipe, Houston decides whether to call it. Detailed semantics, including the safety net for the delete path, in [Task 3 § Phase F](m2-task-3-migrate-deployments-to-cp.md#phase-f--rollback--un-adopt).

Companion install-wide flag `OPERATOR_INHERITANCE_ENABLED` (default `false`) gates **new adoptions** — existing adopted deployments are not affected by `_ENABLED` alone. Both flags are independent and combine as you'd expect.

> Don't add a separate `COMMANDER_ALLOW_SSA` kill-switch. SSA is invoked only when Houston sends `field_manager`, which Houston only does for adopted deployments — both flags above already gate that.

## Discovery / association

Separate from "how do we update", there's "how does Commander find an existing CR to bind to?" Two sub-problems:

1. **Which CRs exist in the cluster?** Commander has cluster-wide RBAC for `airflow.apache.org/v1beta1/airflows` today (operator subchart RBAC; see [`astronomer/charts/astronomer/templates/commander/commander-role.yaml:44-48`](../../../charts/astronomer/templates/commander/commander-role.yaml#L44-L48)) but **no `List` RPC exists** in the existing proto. Existing RPCs (per [`commander/_proto/commander.proto:15-28`](../../../../commander/_proto/commander.proto#L15-L28)): `Ping`, the helm-mode `*Deployment` family, `*Secret`, `*Configmap`, `ApplyCustomResource`, `DeleteCustomResource`, `AirflowMetaCleanup`. No list or get for CRs.
2. **Which Houston deployment does each CR map to?** Today the mapping is `Deployment.releaseName ↔ CR.metadata.name` (per [`houston-api/prisma/schema.prisma`](../../../../houston-api/prisma/schema.prisma) — `releaseName String? @unique`). For adopted CRs we accept whatever name they have and persist it as `releaseName`. See Task 3 for the migration of this mapping.

**Do we need a new RPC for v1?** Yes — but a single-CR `Get`, not a full `List`. The operator enumerates CRs locally via `kubectl get airflows -A` (Houston-driven bulk discovery is not v1), but when they call `adoptDeployment(crNamespace, crName, ...)`, Houston needs to read the live CR spec from the DP to catalogue-map it. Houston fetches it via Commander, not by having the operator round-trip the JSON through the client (stale-paste risk).

Three approaches, ordered by engineering cost:

| # | Approach | Commander change | Notes |
|---|----------|------------------|-------|
| 1 | **Operator passes CR spec into `adoptDeployment` mutation as JSON input.** Houston catalogue-maps it directly. | **None.** | Lowest engineering cost — but the operator round-trips the spec via the client, and a stale paste (between `kubectl get` and the mutation call) silently adopts the wrong shape. **Rejected** in favour of approach 2. |
| 2 | **Add a single-CR ****`GetCustomResource(group, version, plural, namespace, name)`**** RPC** that Commander forwards to the dynamic client's `Get()`. Houston fetches the live CR on the resolver side. | Small. One proto message, one handler, ~20 lines. | Houston is the source of truth for the spec used in catalogue-mapping; operator only supplies identity. **Adopted for v1.** |
| 3 | **Add a full ****`ListCustomResources(group, version, plural, namespaceSelector)`**** RPC** for Houston-driven UI discovery across the whole cluster. | Moderate. Proto + handler + dynamic client `List()` + selector parsing. | Justified only when we add a UI-driven "find my deployments" flow. Not part of v1; revisit once customer feedback warrants it. |

**Recommendation for v1: approach 2.** `GetCustomResource` is the smallest addition that eliminates the stale-paste hazard. The operator drives "which CRs to adopt" externally (`kubectl get airflows -A` to enumerate, then one `astro deployment adopt` per CR). The resolver-side fetch happens transparently to the operator.

## Affected files (initial inventory)

### Proto changes

- [`commander/_proto/custom_resource.proto`](../../../../commander/_proto/custom_resource.proto) — add fields for `field_manager`, `force_apply` on `ApplyCustomResourceRequest`, and a new `GetCustomResource` RPC (required for v1). **`ListCustomResources` is deferred — not part of v1.** _(Use the `grpc-readme-updater` skill when changing these.)_
- [`commander/_proto/commander.proto`](../../../../commander/_proto/commander.proto) — register the new RPC.

### Commander code

- [`commander/api/custom_resource.go`](../../../../commander/api/custom_resource.go) — new handler entry for `GetCustomResource`.
- [`commander/kubernetes/custom_resource.go`](../../../../commander/kubernetes/custom_resource.go) — switch apply path; add list method.
- _(If Option A:)_ replace `Create()` / `Update()` block (lines 35–48) with `Patch` server-side apply.
- _(If Option B:)_ branch on a new request field `adopted bool` to skip the apply.

### Houston code

- [`houston-api/src/lib/deployments/operator/index.js`](../../../../houston-api/src/lib/deployments/operator/index.js) — gate `createOrUpdateDeploymentForOperatorMode()` / `deleteDeploymentForOperatorMode()` on adoption flag (Option B), or trim the emitted spec to APC-owned fields (Option A).
- [`houston-api/src/workers/deployment-upserted-for-create/index.js`](../../../../houston-api/src/workers/deployment-upserted-for-create/index.js)
- [`houston-api/src/workers/deployment-upserted-for-update/index.js`](../../../../houston-api/src/workers/deployment-upserted-for-update/index.js)
- [`houston-api/src/workers/deployment-image-update/`](../../../../houston-api/src/workers/deployment-image-update/)
- [`houston-api/src/workers/deployment-variables-updated/`](../../../../houston-api/src/workers/deployment-variables-updated/)
- [`houston-api/src/workers/deployment-deleted/`](../../../../houston-api/src/workers/deployment-deleted/)

### Optional — operator code

- [`airflow-operator/controllers/airflow/airflow_controller.go`](../../../../airflow-operator/controllers/airflow/airflow_controller.go) — _no change expected_ for Options A/B. If we go with Option C, design the pause/unpause protocol carefully.

## Open questions

- [ ] **Field ownership matrix.** For each top-level field in `Airflow.spec` (executor, scheduler, workers, webserver, …), is APC authoritative, customer authoritative, or shared? This drives whether Option A's slim spec is viable.
- [ ] **Image/runtime version on adoption.** The customer's CR carries `spec.image` already. If they later trigger a runtime upgrade through APC, does the upgrade go through APC's image registry mirror, or do we leave their image source alone?
- [x] **Delete semantics for adopted CRs — resolved.** Two distinct mutations with opposite intent: `deleteDeployment` is fully destructive even for adopted CRs (deletes the CR + namespace + Houston row), and `unadoptDeployment` releases the deployment back to operator-only management without touching K8s. The `deployment-deleted` worker is **not** modified to special-case adopted deployments — destructive intent is preserved. See [Task 3 § Phase F](m2-task-3-migrate-deployments-to-cp.md#phase-f--rollback--un-adopt).
- [ ] **Secrets reconciliation.** Today Commander syncs platform secrets (registry creds, JWT cert, TLS) into the deployment namespace — see [`commander/kubernetes/custom_resource.go`](../../../../commander/kubernetes/custom_resource.go) (lines 1153–1182 per `01-codebase-changes.md`). For adopted namespaces, do we still inject these? Likely yes for registry/JWT, no for things the customer might be managing.
- [ ] **Race with operator's reconcile loop.** Even with server-side apply, the operator may immediately reconcile after our patch and "fight" if its internal state derives from a different spec snapshot. _Needs an integration test._
- [ ] **Detection of "this CR is adopted".** Should it be a CR annotation (e.g. `apc.astronomer.io/adopted-at: 2026-…`) or purely a Houston DB state? Annotation makes it self-describing in-cluster; DB-only keeps the CR pristine.

## Out of scope for this task

- Houston deployment record creation / user mapping → [Task 3](m2-task-3-migrate-deployments-to-cp.md).
- Generating the operator CRD spec on the DP side instead of Houston → [M3 / Task A](m3-task-a-spec-gen-to-commander.md).
- Closing operator-side feature gaps → [M3 / Task D](m3-task-d-close-operator-gaps.md).

## Acceptance criteria (draft)

- [ ] Commander can list existing `Airflow` CRs in a namespace it didn't create.
- [ ] Commander's `ApplyCustomResource` no longer wipes customer-set fields on an adopted CR.
- [ ] An adopted CR's pods are not restarted during association with Commander.
- [ ] Houston exposes an "adopted" status for a deployment (mechanism per Task 3).
- [ ] Update flows from Houston UI (e.g. worker count change) propagate to an adopted CR without disturbing unmanaged fields.
- [ ] Delete flow has a documented contract for adopted CRs.
- [ ] Integration test: end-to-end loop — create CR with `kubectl`, register in Houston, edit via Houston, verify CR reflects edit and customer-set field is preserved.
