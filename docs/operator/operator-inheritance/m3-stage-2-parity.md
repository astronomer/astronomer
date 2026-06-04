# M3 — Stage 2: Bringing close parity in operator and helm in APC

**Linear milestone:** Stage 2: Bringing close parity in operator and helm in APC
**Parent project:** [Operator Inheritance](https://linear.app/astronomer/project/operator-inheritance-6426e0c693ab)
**Status:** Planning — no Linear issues filed yet
**Owner:** _TBD_

> Linked Linear milestone description (verbatim):
> *"There are several architecture and parity gaps in the APC helm and operator and between the APC versions (0.37.x and 1.0+). We need to close the gaps on the APC side and maybe do some development on the operator code."*
>
> *Gap analysis:* [`../03-gap-analysis.md`](../03-gap-analysis.md)
>
> *We need to perform the following things:*
>
> *a. Changes in APC 1.0+: The responsibility of spec generation and applying it lied on the houston (CP service). After 1.0, the responsibility should be shifted to commander (DP service) since the Operator CRD will be applied in the DP. So we need to migrate operator related code to commander.*
>
> *b. Upgrade the operator to v16+: Current APC 0.37.x supports operator version 1.15.6. We need to upgrade the operator version to 16.x. This is a low priority task in this stage as this would mean just bump the operator version (installing latest version of operator). There may not be many breaking changes since this is a minor bump, but we need to confirm this with Ian.*
>
> *c. Closing the gap in APC: On the document in the gap analysis, we can achieve closing certain gaps on the APC side. This is something we can do easily.*
>
> *d. Closing the parity gap in operator: There are certain features (like git sync and mysql support) which is currently (or in future like laminar) may not work. We may need to do some development on the operator and we can de-prioritize certain features or prioritize them in future releases. We need to scope these features in releases and need to decide what needs to be scoped for the v1 of this project.*

---

## Goal

Bring the operator-mode deployment experience to feature parity with the helm-mode experience inside APC, **and** repair the architectural mismatch that operator code currently sits on the CP (Houston) while CRD application lives on the DP (Commander).

In other words: a customer using operator-mode deployments should feel no missing features vs helm-mode, and the codebase should reflect APC 1.0+'s CP/DP boundary cleanly.

## Why now

- M2 (this project's previous milestone) makes operator-mode the **primary** mode for adopted customers. Anything that's "best-effort" today becomes load-bearing.
- APC 1.0+ moved deployment runtime into the DP. Houston still owns operator CRD generation — see [`houston-api/src/lib/deployments/operator/index.js`](../../../../houston-api/src/lib/deployments/operator/index.js) (1498 lines, generates the full Airflow CR spec). That's CP-side code applying DP-side resources via a thin Commander RPC. With adopted deployments multiplying, the seam is worth fixing.
- The 19 gaps catalogued in [`../03-gap-analysis.md`](../03-gap-analysis.md) span multiple priorities and codebases; M3 is where they get scheduled.

## Tasks in this milestone

| # | Task | Doc |
|---|------|-----|
| A | Move operator CRD spec generation from Houston to Commander | [`m3-task-a-spec-gen-to-commander.md`](m3-task-a-spec-gen-to-commander.md) |
| B | Upgrade the Astro Runtime Operator to v1.6.x / v16.x | [`m3-task-b-upgrade-operator-v16.md`](m3-task-b-upgrade-operator-v16.md) |
| C | Close APC-side parity gaps from the gap analysis | [`m3-task-c-close-apc-gaps.md`](m3-task-c-close-apc-gaps.md) |
| D | Close operator-side parity gaps from the gap analysis | [`m3-task-d-close-operator-gaps.md`](m3-task-d-close-operator-gaps.md) |

These tasks are partially independent. Suggested ordering:

1. **B first.** Picking the operator version we're targeting unblocks A (proto contracts) and changes the surface for C/D. The milestone description marks B as low priority on its own, but it's a prerequisite for the rest of M3.
2. **A and D in parallel.** A is a CP/DP architectural shift; D is operator-repo feature work. They touch different teams.
3. **C last (or alongside).** Most C-gaps are small chart/config fixes; some block other work (e.g. [`../03-gap-analysis.md`](../03-gap-analysis.md) Gap 1 / Gap 16 — MySQL probe config).

## What's already known

From the existing project docs (which cover APC 2.0's "Install APC using an Operator" — a different but adjacent effort):

| Doc | Content |
|-----|---------|
| [`../01-codebase-changes.md`](../01-codebase-changes.md) | Repo-by-repo inventory of what exists and what's pending. |
| [`../02-local-setup.md`](../02-local-setup.md) | k3d-based local setup with operator enabled. |
| [`../03-gap-analysis.md`](../03-gap-analysis.md) | 19 gaps with priority (P0..P3) and effort (S..XL). |

These docs were authored for the APC 2.0 effort; M3 inherits their content as background but moves the gap-closing work forward.

## How the 19 gaps map onto M3 sub-tasks

| Gap (from [`../03-gap-analysis.md`](../03-gap-analysis.md)) | Priority | Side | M3 sub-task |
|---|---|---|---|
| 1 — Houston missing MySQL probe config | P0 | APC | C |
| 2 — Airflow 3.x support in CRD generation | P0 | APC + Operator | A (rewritten in Commander) + D |
| 3 — Operator image version mismatch | P0 | APC | B |
| 4 — Commander imagePullSecret bug | P1 | APC | C |
| 5 — Silent secret sync failures | P1 | APC | C |
| 6 — Disabling SA / Role / RoleBindings | P1 | Operator | D |
| 7 — Removal of cluster roles/bindings | P2 | Operator | D (docs-only or namespace-scoped mode) |
| 8 — Platform-level Network Policy | P1 | Operator + APC | D (primary), C (chart wiring) |
| 9 — PlatformNodePool (pod separation) | P2 | Operator | D |
| 10 — DAGs server | P1 | Operator | D |
| 11 — DAG deployment method | P1 | APC + Operator | C + D |
| 12 — Git sync | P2 | Operator | D |
| 13 — Resource Quota mechanism | P2 | APC | C |
| 14 — OpenShift integration (first class) | P2 | Operator | D |
| 15 — Enabling/disabling Triggerer | P1 | Operator | D |
| 16 — MySQL liveness/readiness probes | P1 | APC | C |
| 17 — Celery Flower UI | P3 | Operator | D (defer) |
| 18 — CLI support for operator mode | P2 | APC | C |
| 19 — Laminar auth coupling | Info | Operator | — (not in scope) |

## Open questions for this milestone

- [ ] **Target operator version.** v1.6.x (the rc currently in the repo) vs v1.16.x (mentioned in milestone description). Pinning matters before A/C/D can land. _(Owner: Karan + Ian.)_
- [ ] **Phased shipment.** Does the spec-gen migration (A) ship in the same APC release as the operator bump (B)? They could decouple, but each touches the others' integration tests.
- [ ] **Backwards compatibility.** APC 0.37.x → 2.x upgraders may have operator-mode deployments today. Do those keep using the Houston-generated spec post-migration, or get re-emitted by Commander?
- [ ] **Deferred gaps.** Which P2/P3 items can be cut from M3's MVP without missing the GA bar for the Operator Inheritance project?
- [ ] **Performance/scale.** Customer use cases (Deutsche Bank, ~750 deployments) imply Commander handling many CRs concurrently. Spec-gen-in-Commander adds CPU; need a back-of-envelope sizing.

## Out of scope for this milestone

- Adoption of pre-existing operator CRs by Commander → that's [M2 / Task 2](m2-task-2-connect-operator-to-commander.md). M3 assumes APC creates the CRs.
- The PRD's "discovery + register" UX → also M2 ([Task 3](m2-task-3-migrate-deployments-to-cp.md)).
- Laminar / AstroExecutor parity — see Gap 19; deferred.

## Risks

| Risk | Severity | Notes |
|------|----------|-------|
| Spec-gen migration is bigger than estimated (1498 lines + dependencies) | High | See [Task A](m3-task-a-spec-gen-to-commander.md). |
| Operator bump introduces undocumented breaking changes | Medium | Reading `airflow-operator/CHANGELOG.md` confirms structured release notes exist; verify with Ian. |
| Closing operator gaps requires synchronized releases of `airflow-operator` and APC | Medium | Coordination cost; addressed by versioning + feature flags. |
| Some gaps (e.g. OpenShift parity, Gap 14) are larger than M3 timeline | High | Phase across releases; see [Task D](m3-task-d-close-operator-gaps.md). |
