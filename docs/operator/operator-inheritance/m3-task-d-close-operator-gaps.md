# M3 / Task D — Close operator-side parity gaps

**Parent milestone:** [M3 — Stage 2 parity](m3-stage-2-parity.md)
**Linear issue:** _not yet filed_
**Owner:** _TBD (coordinate with the operator team)_
**Effort:** _Per-gap; see table below._

> Linked Linear milestone description (verbatim):
> *"Closing the parity gap in operator: There are certain features (like git sync and mysql support) which is currently (or in future like laminar) may not work. We may need to do some development on the operator and we can de-prioritize certain features or prioritize them in future releases. We need to scope these features in releases and need to decide what needs to be scoped for the v1 of this project."*

---

## Goal

Burn down the subset of [`../03-gap-analysis.md`](../03-gap-analysis.md) gaps that need changes inside the [`airflow-operator/`](../../../../airflow-operator/) repo. Coordinate with the operator team on release scoping — which gaps land in which Astro Runtime Operator release.

This doc **does not duplicate the gap analysis** — it links into it, identifies the operator-side subset, and adds task-level context (where the change lands, ordering, dependencies).

Companion: APC-side gaps live in [`m3-task-c-close-apc-gaps.md`](m3-task-c-close-apc-gaps.md).

> The gap analysis was authored for the previous "Install APC using an Operator" Linear project (APC 2.0). Per [`00-overview.md`](00-overview.md), [`../03-gap-analysis.md`](../03-gap-analysis.md) stays as-is; this doc inherits its findings.

---

## Gaps in scope (operator-side)

| Gap | Priority | Brief | Effort | Link |
|-----|----------|-------|--------|------|
| 2 (partial) | P0 | Airflow 3.x support (APIServer / EventScheduler) | M | [Gap 2 →](../03-gap-analysis.md#gap-2-airflow-3x-support-in-crd-generation-gap-2) |
| 6 | P1 | Disabling SA / Role / RoleBindings | M | [Gap 6 →](../03-gap-analysis.md#gap-6-disabling-sa-role-rolebindings-gap-6) |
| 7 | P2 | Removal of cluster roles/bindings (constraint or namespace-scoped mode) | L (or S as docs-only) | [Gap 7 →](../03-gap-analysis.md#gap-7-removal-of-cluster-rolesbindings-gap-7) |
| 8 (primary) | P1 | Platform-level NetworkPolicy for all components | M | [Gap 8 →](../03-gap-analysis.md#gap-8-platform-level-network-policy-gap-8) |
| 9 | P2 | PlatformNodePool (pod separation) | M | [Gap 9 →](../03-gap-analysis.md#gap-9-platformnodepool-pod-separation-gap-9) |
| 10 | P1 | DAGs server as a CRD component (vs k8sManifests workaround) | L | [Gap 10 →](../03-gap-analysis.md#gap-10-dags-server-gap-10) |
| 11 (operator side) | P1 | Native DAG deployment method support in CRD | M | [Gap 11 →](../03-gap-analysis.md#gap-11-dag-deployment-method-gap-11) |
| 12 | P2 | Git sync sidecar | M | [Gap 12 →](../03-gap-analysis.md#gap-12-git-sync-gap-12) |
| 14 | P2 | OpenShift first-class support | XL | [Gap 14 →](../03-gap-analysis.md#gap-14-openshift-integration-first-class-gap-14) |
| 15 | P1 | Enabling/disabling Triggerer | S | [Gap 15 →](../03-gap-analysis.md#gap-15-enablingdisabling-triggerer-gap-15) |
| 17 | P3 | Celery Flower UI as a component | S | [Gap 17 →](../03-gap-analysis.md#gap-17-celery-flower-ui-gap-17) |

APC-side gaps (1, 3, 4, 5, 13, 16, 18) → [Task C](m3-task-c-close-apc-gaps.md).
Gap 19 (Laminar) is out of scope per the gap analysis.

---

## Per-gap notes for operator implementation

The numbered subsections below add detail beyond what's in [`../03-gap-analysis.md`](../03-gap-analysis.md) — pointers into specific files, scope boundaries, and dependencies. Open the linked gap-analysis section for problem statement + remediation path.

### Gap 2 (operator-side) — Airflow 3.x

**See:** [Gap 2 in gap analysis](../03-gap-analysis.md#gap-2-airflow-3x-support-in-crd-generation-gap-2).

**Operator-side scope:**
- Confirm `apiServer` (AF 3.x) and `eventScheduler` (AstroExecutor) fields exist in [`airflow-operator/apis/airflow/v1beta1/airflow_types.go`](../../../../airflow-operator/apis/airflow/v1beta1/airflow_types.go) and have validation/defaulting webhooks.
- Verify the controller materializes both webserver (AF 2.x) and apiServer (AF 3.x) paths.

**Coordinates with:** [`m3-task-c-close-apc-gaps.md`](m3-task-c-close-apc-gaps.md) Gap 2 (Houston/Commander side emits the right one).

### Gap 6 — Disable SA / Role / RoleBindings

**See:** [Gap 6 in gap analysis](../03-gap-analysis.md#gap-6-disabling-sa-role-rolebindings-gap-6).

**Operator-side scope:**
- Add `rbac.create: false` (or similar) field to the Airflow CRD.
- Update the RBAC controller to skip creation when disabled. (Controller location: [`airflow-operator/controllers/airflow/airflow_controller.go`](../../../../airflow-operator/controllers/airflow/airflow_controller.go) and likely a dedicated RBAC reconciler in [`airflow-operator/internal/airflow/`](../../../../airflow-operator/internal/airflow/).)
- Document the pre-provisioned resource names the customer must create.

**Customer drivers:** Ford, RBC per gap analysis.

### Gap 7 — Cluster roles / bindings constraint

**See:** [Gap 7 in gap analysis](../03-gap-analysis.md#gap-7-removal-of-cluster-rolesbindings-gap-7).

**Operator-side scope:**
- Option A — accept as a constraint, document the minimum ClusterRole.
- Option B — implement / verify namespace-scoped mode. The operator already supports `--namespaces` (per gap analysis); confirm this in [`airflow-operator/main.go`](../../../../airflow-operator/main.go) and document the recipe.

**Recommendation in gap analysis:** docs-only for now.

### Gap 8 (operator-side) — NetworkPolicy

**See:** [Gap 8 in gap analysis](../03-gap-analysis.md#gap-8-platform-level-network-policy-gap-8).

**Operator-side scope:**
- Today: only StatsD and PgBouncer support `enableNetworkPolicy`.
- Add CRD fields + reconcilers for: Scheduler, Webserver/APIServer, Workers, Triggerer, Redis, DAGProcessor.
- Field shape: `networkPolicy: { enabled: bool, rules: [...] }` per component or a top-level switch.

**Coordinates with:** [`m3-task-c-close-apc-gaps.md`](m3-task-c-close-apc-gaps.md) Gap 8 wiring.

### Gap 9 — PlatformNodePool

**See:** [Gap 9 in gap analysis](../03-gap-analysis.md#gap-9-platformnodepool-pod-separation-gap-9).

**Operator-side scope:**
- Audit component specs in [`airflow-operator/apis/airflow/v1beta1/`](../../../../airflow-operator/apis/airflow/v1beta1/) for `nodeSelector` / `affinity` / `tolerations`.
- Add missing fields. Verify controllers thread them through to pod specs.

### Gap 10 — DAGs server

**See:** [Gap 10 in gap analysis](../03-gap-analysis.md#gap-10-dags-server-gap-10).

**Choice point:**
- (a) Add a `dagsServer` component to the Airflow CR (+ controller).
- (b) Keep the current APC-side `k8sManifests` workaround (Houston emits raw K8s YAML).

If (a) is chosen, the existing handlebars templates in [`houston-api/src/lib/deployments/operator/manifests/dag-only-deploy/`](../../../../houston-api/src/lib/deployments/operator/manifests/dag-only-deploy/) become deprecated; [`m3-task-a-spec-gen-to-commander.md`](m3-task-a-spec-gen-to-commander.md) and [`m3-task-c-close-apc-gaps.md`](m3-task-c-close-apc-gaps.md) Gap 11 both consume this decision.

### Gap 11 (operator-side) — DAG deployment method

**See:** [Gap 11 in gap analysis](../03-gap-analysis.md#gap-11-dag-deployment-method-gap-11).

**Operator-side scope:** if Gap 10 ships (a), a `dagDeployment` section on the CR replaces the k8sManifests workaround. Same field needs validation + defaulting.

### Gap 12 — Git sync

**See:** [Gap 12 in gap analysis](../03-gap-analysis.md#gap-12-git-sync-gap-12).

**Operator-side scope:**
- Add git-sync sidecar config to Scheduler and Worker component specs.
- Fields: repo URL, branch, sync interval, credentials secret reference.

**Customer drivers:** the gap analysis marks this P2 since image-based and DAG-only are viable alternatives.

### Gap 14 — OpenShift first-class

**See:** [Gap 14 in gap analysis](../03-gap-analysis.md#gap-14-openshift-integration-first-class-gap-14).

**Operator-side scope (large):**
- Audit pod security contexts in all components for `restricted-v2` SCC compatibility (non-root UID, no privilege escalation, allowed capabilities).
- Add Route resources (in addition to / instead of Ingress) where appropriate.
- OpenShift-specific CI pipeline.
- The operator already has an `--openshift` flag — see [`airflow-operator/main.go`](../../../../airflow-operator/main.go). Audit what it actually does today.

**Note:** Gap analysis lists this as XL. Likely needs to be scoped across multiple releases. Decide what's "first-class enough" for v1.

### Gap 15 — Triggerer enable/disable

**See:** [Gap 15 in gap analysis](../03-gap-analysis.md#gap-15-enablingdisabling-triggerer-gap-15).

**Operator-side scope:** controller must respect `triggerer.replicas: 0` or `triggerer: null` by tearing down the StatefulSet/Deployment. Known bug per [astronomer/issues#6857](https://github.com/astronomer/issues/issues/6857).

Small fix; should be one of the first to land.

### Gap 17 — Flower

**See:** [Gap 17 in gap analysis](../03-gap-analysis.md#gap-17-celery-flower-gap-17).

**Operator-side scope:** add Flower as an optional component, or defer (gap analysis marks P3).

---

## Sequencing

Coordinate with the operator team. Suggested order:

1. **Gap 15** (Triggerer enable/disable) — small, P1, known bug.
2. **Gap 6** (RBAC disable knob) — required by named enterprise customers.
3. **Gap 8** (NetworkPolicy for all components) — required by enterprise security.
4. **Gap 2** (AF 3.x in CRD) — coordinate with [Task A](m3-task-a-spec-gen-to-commander.md).
5. **Gap 10 + 11** (DAGs server + DAG deployment method) — make a decision on architecture first; either deepens or removes the APC-side `k8sManifests` path.
6. **Gap 9** (PlatformNodePool fields) — fairly mechanical once CRD types know about scheduling constraints.
7. **Gap 12** (Git sync) — P2.
8. **Gap 14** (OpenShift first-class) — phased across releases.
9. **Gap 17** (Flower) — defer or skip.

## Open questions

- [ ] **Operator release cadence vs APC.** Several gaps need synchronized releases (CRD field added in operator → field consumed in Houston/Commander). What's the coordination model? *(Owner: APC + Operator)*
- [ ] **Backward-compatibility of CRD changes.** New optional fields are safe. Renames or removals are not. Need a policy: never break, always-additive.
- [ ] **OpenShift scope.** What counts as "first-class" — security contexts only, or Routes too? Customer-specific?
- [ ] **DAGs server: native component vs sidecar pattern.** Choice affects [`m3-task-a-spec-gen-to-commander.md`](m3-task-a-spec-gen-to-commander.md) and [`m3-task-c-close-apc-gaps.md`](m3-task-c-close-apc-gaps.md) Gap 11.
- [ ] **Operator's existing `--namespaces` flag.** Does namespace-scoped mode actually work today (Gap 7)? Needs verification before claiming the constraint is documented-only.

## Out of scope

- APC-side fixes → [Task C](m3-task-c-close-apc-gaps.md).
- Operator image bump → [Task B](m3-task-b-upgrade-operator-v16.md).
- Architectural Houston→Commander migration → [Task A](m3-task-a-spec-gen-to-commander.md).

## Acceptance criteria (draft)

- [ ] Gap 15 fixed in a near-term operator release.
- [ ] Gaps 2, 6, 8, 10, 11 (P0/P1) shipped in the operator release that pairs with the M3 APC release.
- [ ] Gap 9, 12, 14 scoped and tracked across subsequent operator releases.
- [ ] Each closed gap has an integration test in [`airflow-operator/integration-tests/`](../../../../airflow-operator/integration-tests/).
- [ ] CRD field additions are documented in operator release notes.
- [ ] [`../03-gap-analysis.md`](../03-gap-analysis.md) left untouched per scope decision in [`00-overview.md`](00-overview.md).
