# M3 / Task C — Close APC-side parity gaps

**Parent milestone:** [M3 — Stage 2 parity](m3-stage-2-parity.md)
**Linear issue:** _not yet filed_
**Owner:** _TBD (APC team)_
**Effort:** _Per-gap; see table below._

> Linked Linear milestone description (verbatim):
> *"Closing the gap in APC: On the document in the gap analysis, we can achieve closing certain gaps on the APC side. This is something we can do easily."*

---

## Goal

Burn down the subset of [`../03-gap-analysis.md`](../03-gap-analysis.md) gaps whose remediation lives in APC repos — `astronomer/` (chart), `houston-api/`, `commander/`, `apc-ui/`, `astro-cli/`. Operator-side gaps are covered in [`m3-task-d-close-operator-gaps.md`](m3-task-d-close-operator-gaps.md).

This doc **does not duplicate the gap analysis** — it links into it, identifies the APC-side subset, and adds task-level context (where the fix goes, ordering, dependencies).

> The gap analysis was authored for the previous "Install APC using an Operator" Linear project (APC 2.0). Per [`00-overview.md`](00-overview.md), [`../03-gap-analysis.md`](../03-gap-analysis.md) stays as-is; this doc inherits its findings.

---

## Gaps in scope (APC-side)

| Gap | Priority | Repos | Brief | Link |
|-----|----------|-------|-------|------|
| 1 | P0 | astronomer, houston-api | Houston missing MySQL probe config | [Gap 1 →](../03-gap-analysis.md#gap-1-houston-missing-mysql-probe-config-gap-1) |
| 2 | P0 | houston-api (+ operator) | Airflow 3.x support in CRD generation | [Gap 2 →](../03-gap-analysis.md#gap-2-airflow-3x-support-in-crd-generation-gap-2) |
| 3 | P0 | astronomer | Operator image version mismatch — _superseded by [Task B](m3-task-b-upgrade-operator-v16.md)_ | [Gap 3 →](../03-gap-analysis.md#gap-3-operator-image-version-mismatch-gap-3) |
| 4 | P1 | commander | Commander imagePullSecret bug | [Gap 4 →](../03-gap-analysis.md#gap-4-commander-imagepullsecret-assignment-bug-gap-4) |
| 5 | P1 | commander | Silent secret sync failures | [Gap 5 →](../03-gap-analysis.md#gap-5-silent-secret-sync-failures-gap-5) |
| 8 (partial) | P1 | astronomer | NetworkPolicy wiring through chart | [Gap 8 →](../03-gap-analysis.md#gap-8-platform-level-network-policy-gap-8) |
| 11 (partial) | P1 | houston-api | DAG deployment method — CRD-side wiring | [Gap 11 →](../03-gap-analysis.md#gap-11-dag-deployment-method-gap-11) |
| 13 | P2 | astronomer, houston-api | Resource Quota mechanism | [Gap 13 →](../03-gap-analysis.md#gap-13-resource-quota-mechanism-gap-13) |
| 16 | P1 | astronomer | MySQL liveness/readiness probes (same root as Gap 1) | [Gap 16 →](../03-gap-analysis.md#gap-16-mysql-livenessreadiness-probes-gap-16) |
| 18 | P2 | astro-cli | CLI support for operator mode | [Gap 18 →](../03-gap-analysis.md#gap-18-cli-support-for-operator-mode-gap-18) |

Operator-side gaps (6, 7, 8 primary, 9, 10, 12, 14, 15, 17) → [Task D](m3-task-d-close-operator-gaps.md).
Gap 19 (Laminar) is out of scope per the gap analysis.

---

## Per-gap notes for APC implementation

The numbered subsections below add detail beyond what's in [`../03-gap-analysis.md`](../03-gap-analysis.md) — pointers into specific files, scope boundaries, and ordering caveats. Open the gap-analysis section linked in each header for problem statement + remediation path.

### Gap 1 — MySQL probe config in houston-configmap

**See:** [Gap 1 in gap analysis](../03-gap-analysis.md#gap-1-houston-missing-mysql-probe-config-gap-1) and [Gap 16](../03-gap-analysis.md#gap-16-mysql-livenessreadiness-probes-gap-16) (same root cause).

**Touch points:**
- [`astronomer/charts/astronomer/templates/houston/houston-configmap.yaml:99-101`](../../../charts/astronomer/templates/houston/houston-configmap.yaml#L99-L101) — today only passes `deployments.mode.operator.enabled`.
- [`astronomer/charts/astronomer/values.yaml`](../../../charts/astronomer/values.yaml) — add `astronomer.houston.config.deployments.mode.operator.{scheduler,workers,triggerer,webserver,apiServer}.mysql.{livenessProbe,readinessProbe}` blocks with sensible defaults.
- [`houston-api/src/lib/deployments/operator/index.js:250-272`](../../../../houston-api/src/lib/deployments/operator/index.js#L250-L272) — already reads these paths.

**Ordering:** ideally land before any MySQL-backed operator deployment ships. P0.

**Note:** if [Task A](m3-task-a-spec-gen-to-commander.md) moves spec-gen to Commander before this fixes ships, the new configmap lives in `commander-configmap.yaml` instead.

### Gap 2 — Airflow 3.x in CRD generation

**See:** [Gap 2 in gap analysis](../03-gap-analysis.md#gap-2-airflow-3x-support-in-crd-generation-gap-2).

**Touch points (APC side):**
- [`houston-api/src/lib/deployments/operator/index.js:728`](../../../../houston-api/src/lib/deployments/operator/index.js#L728) — `getCRDSpecFromHelmValues()` must conditionally include `apiServer` (AF 3.x) vs `webserver` (AF 2.x).
- The chart's runtime-version mapping (location _TBD_) — when does AF 3.x become the default for a deployment?

**Cross-cutting:** also touches operator-side validation — see [Task D](m3-task-d-close-operator-gaps.md). Coordinate version boundary with operator team.

### Gap 3 — Operator image version

Covered by [Task B](m3-task-b-upgrade-operator-v16.md). No separate work here.

### Gap 4 — Commander `imagePullSecret` bug

**See:** [Gap 4 in gap analysis](../03-gap-analysis.md#gap-4-commander-imagepullsecret-assignment-bug-gap-4).

**Touch points:**
- [`commander/kubernetes/custom_resource.go`](../../../../commander/kubernetes/custom_resource.go) — around line 1228 per the gap analysis. Variable assignment looks like `image = …` where `imagePullSecret = …` was intended.
- Add unit test covering the extraction path.

**Note on file references:** the existing `01-codebase-changes.md` cites `commander/kubernetes/custom_resource.go:1228`, but the recon also surfaced the apply logic in `commander/provisioner/kubernetes/kubernetes.go:1333`. Confirm which file has the bug before fixing.

### Gap 5 — Silent secret sync failures

**See:** [Gap 5 in gap analysis](../03-gap-analysis.md#gap-5-silent-secret-sync-failures-gap-5).

**Touch points:**
- [`commander/kubernetes/custom_resource.go`](../../../../commander/kubernetes/custom_resource.go) — lines 1153–1182 per the gap analysis. Classify secrets as critical/optional; fail-on-critical-error.

**Adoption interaction:** in M2's adopted-deployment world, these secrets might already exist (customer created them) or might exist with a different name. Reconcile carefully — see open question.

### Gap 8 (APC-side wiring) — Platform-level NetworkPolicy

**See:** [Gap 8 in gap analysis](../03-gap-analysis.md#gap-8-platform-level-network-policy-gap-8).

**APC-side scope:** the operator-side change (Task D) adds NetworkPolicy fields to the CRD. The APC side wires these through:
- [`houston-api/src/lib/deployments/operator/index.js`](../../../../houston-api/src/lib/deployments/operator/index.js) — emit network-policy fields based on chart toggle.
- [`astronomer/charts/astronomer/templates/houston/houston-configmap.yaml`](../../../charts/astronomer/templates/houston/houston-configmap.yaml) — add `deployments.mode.operator.networkPolicy.{enabled,rules}` defaults.

### Gap 11 (APC-side) — DAG deployment method

**See:** [Gap 11 in gap analysis](../03-gap-analysis.md#gap-11-dag-deployment-method-gap-11).

**APC-side scope:** Houston already generates `k8sManifests` for DAG-server resources alongside the Airflow CR (see `houston-api/src/lib/deployments/operator/manifests/dag-only-deploy/`). Verify the manifests it emits match the current DAG server. If we move spec-gen to Commander ([Task A](m3-task-a-spec-gen-to-commander.md)), the manifest generation moves too. Coordinate with the operator-side decision in [Task D](m3-task-d-close-operator-gaps.md) Gap 10 — if the operator gains a native DAG-server component, the APC-side `k8sManifests` path becomes vestigial.

### Gap 13 — Resource Quota mechanism

**See:** [Gap 13 in gap analysis](../03-gap-analysis.md#gap-13-resource-quota-mechanism-gap-13).

**Touch points:**
- Commander side: add a step to `ApplyCustomResource` (or the new RPC from Task A) that creates a K8s `ResourceQuota` in the deployment namespace.
- Houston side: surface quota values via [`upsertDeployment.quotas`](../../../../houston-api/src/schema/mutation.js#L683-L792).
- Chart side: defaults under `deployments.mode.operator.resourceQuota.*` in houston-configmap.

### Gap 16 — MySQL liveness/readiness probes

Same root cause as Gap 1. Track together.

### Gap 18 — CLI support for operator mode

**See:** [Gap 18 in gap analysis](../03-gap-analysis.md#gap-18-cli-support-for-operator-mode-gap-18).

**Touch points:**
- [`astro-cli/cmd/software/deployment.go:141-170`](../../../../astro-cli/cmd/software/deployment.go#L141-L170) — `newDeploymentCreateCmd()`. Add `--mode operator`.
- Same file — add `astro deployment inspect` operator-aware output.
- New / existing files for `astro deploy` (DAG deployment) — verify it works with operator deployments.

**Cross-cutting:** the M2 / Task 3 adoption flow also lands in the CLI (`astro deployment discover`, `astro deployment adopt`). Decide whether to ship them together or separately.

---

## Sequencing

Within Task C, suggested order:

1. **Gaps 1 + 16** (MySQL probe config) — chart-only, unblocks MySQL customers immediately.
2. **Gap 4** (imagePullSecret) — small commander fix.
3. **Gap 5** (secret sync hardening) — bigger commander change; needs care w.r.t. adopted deployments.
4. **Gap 2** (AF 3.x) — coordinate with operator team; possibly merge with [Task A](m3-task-a-spec-gen-to-commander.md) since both touch the spec generator.
5. **Gap 8** (NetworkPolicy chart wiring) — wait for Task D operator-side work.
6. **Gap 11** (DAG deployment method) — coordinate with Task A and Task D Gap 10.
7. **Gap 13** (ResourceQuota) — independent, sequence after MVP.
8. **Gap 18** (CLI) — independent, can run in parallel.

## Open questions

- [ ] **Should Gaps 1 + 16 be backported to 0.37.x?** They're documented as P0 for any MySQL operator deployment. _(Owner: APC PM.)_
- [ ] **Spec-gen location for Gap 2.** If [Task A](m3-task-a-spec-gen-to-commander.md) is in flight, fix Gap 2 once in Commander rather than fixing once in Houston and again in Commander.
- [ ] **Resource quota source-of-truth.** Houston-driven or chart-driven defaults? Customers' existing operator deployments may already have quotas (in M2 adoption flow).
- [ ] **CLI shape for adoption + operator mode.** `astro deployment create --mode operator` vs `astro deployment adopt --mode operator` overlap. Single command with flags, or two?

## Out of scope

- Operator-side fixes → [Task D](m3-task-d-close-operator-gaps.md).
- The operator version bump itself → [Task B](m3-task-b-upgrade-operator-v16.md).
- Architectural Houston→Commander migration → [Task A](m3-task-a-spec-gen-to-commander.md).

## Acceptance criteria (draft)

- [ ] Gaps 1, 4, 5, 16 (P0/P1) closed and tested.
- [ ] Gap 2 closed in whichever code location owns spec-gen at ship time.
- [ ] Gap 8 APC-side wiring shipped after Task D operator-side change.
- [ ] Gap 11, 13, 18 closed before GA of Operator Inheritance.
- [ ] Each closed gap has a regression test (chart test, unit test, or integration test).
- [ ] `../03-gap-analysis.md` left untouched per scope decision in [`00-overview.md`](00-overview.md).
