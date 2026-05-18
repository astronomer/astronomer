# Operator Inheritance — Design Doc Index

**Linear Project:** [Operator Inheritance](https://linear.app/astronomer/project/operator-inheritance-6426e0c693ab)
**PRD:** [Land-and-Expand Architecture](https://linear.app/astronomer/document/prd-land-and-expand-architecture-5d7296ddda41)
**Target Release:** APC 2.1 (target: 2026-07-31)
**Lead:** Karan Khanchandani
**Status:** In Progress
**Priority:** High

---

## Purpose

This folder contains design docs for the **Operator Inheritance** initiative — letting APC "layer onto" an existing Astro Runtime Operator install rather than provisioning everything from scratch. The end-state is a phased adoption motion:

1. Customer adopts the Astro Runtime Operator (migrate from self-managed OSS Airflow).
2. APC's control plane and data plane layer on top of the existing Operator deployments.
3. The customer scales additional Astro Runtime deployments through APC.

See the PRD for product/business framing. The docs in this folder are engineering-side design.

---

## Scope of these design docs

| Milestone | In-scope here? | Notes |
|-----------|----------------|-------|
| Cancelled: POC — [Stage 0 → 1] Manage OSS deployments via Astro Runtime Operator | No | De-scoped — field engineering will own the Stage 0 → 1 conversion. |
| [Stage 1 → 2] Astro Runtime operator to APC adoption | **Yes** | See [M2 docs](#milestone-2--stage-1--2-astro-runtime-operator-to-apc-adoption). |
| Stage 2: Bringing close parity in operator and helm in APC | **Yes** | See [M3 docs](#milestone-3--stage-2-bringing-close-parity-in-operator-and-helm-in-apc). |

---

## Milestone 2 — [Stage 1 → 2] Astro Runtime operator to APC adoption

The Operator (and its Airflow CRDs) already exist in a Kubernetes cluster when APC arrives. APC needs to install the DP into that cluster, connect Commander to the existing CRDs, and pull the deployments into Houston's data model.

- **[M2 — Milestone overview](m2-stage-1-to-2-adoption.md)**
- [M2 / Task 1: Install the APC data plane onto the operator's cluster](m2-task-1-install-dp.md)
- [M2 / Task 2: Connect existing operator CRDs to Commander](m2-task-2-connect-operator-to-commander.md)
- [M2 / Task 3: Migrate Airflow deployments into the APC control plane](m2-task-3-migrate-deployments-to-cp.md)

> No Linear issues exist for these tasks yet. Task IDs and assignees will be populated once the issues are filed.

---

## Milestone 3 — Stage 2: Bringing close parity in operator and helm in APC

There are architecture and parity gaps between (a) the operator and helm modes in APC, and (b) APC 0.37.x vs APC 1.0+. Closing them means moving spec generation onto the DP, bumping the operator, and burning down the gap list.

- **[M3 — Milestone overview](m3-stage-2-parity.md)**
- [M3 / Task A: Move operator CRD spec generation from Houston to Commander (APC 1.0+)](m3-task-a-spec-gen-to-commander.md)
- [M3 / Task B: Upgrade the Astro Runtime Operator to v1.6.x / v16.x](m3-task-b-upgrade-operator-v16.md)
- [M3 / Task C: Close APC-side parity gaps](m3-task-c-close-apc-gaps.md)
- [M3 / Task D: Close operator-side parity gaps](m3-task-d-close-operator-gaps.md)

Task C and D both build on the gap inventory in [`../03-gap-analysis.md`](../03-gap-analysis.md) (from the prior "Install APC using an Operator" project). That doc is intentionally not modified by this project — these new docs link to it.

---

## Related documents in this repo

| Doc | Project / context | Relationship |
|-----|------|--------------|
| [`../01-codebase-changes.md`](../01-codebase-changes.md) | Install APC using an Operator (APC 2.0) | Reference for "what exists today" across repos. |
| [`../02-local-setup.md`](../02-local-setup.md) | Install APC using an Operator (APC 2.0) | Local dev environment for testing operator-mode deployments. |
| [`../03-gap-analysis.md`](../03-gap-analysis.md) | Install APC using an Operator (APC 2.0) | 19-gap inventory; feeds M3 Tasks C & D. |

---

## Cross-cutting open questions

These cut across multiple tasks and need product/architecture input before the dependent docs can be finalized.

- [ ] **Pricing/licensing:** Does an adopted deployment count against the customer's APC license? Separate SKU? *(Owner: Nic Slattery / Pranav Bahadur — per PRD)*
- [ ] **Operator CRD adoption timing:** P1 or P2? Affects whether parity work (M3) must complete before adoption (M2) can ship. *(Owner: TBD)*
- [ ] **Commander "observe and augment" vs "provision and own":** How invasive are the Commander changes? This is the largest engineering risk per PRD. *(Owner: Karan Khanchandani / Adhip Joshi)*
- [ ] **Houston model — adopted vs native:** New column, or derived from provisioning method? See M2 / Task 3.
- [ ] **Relationship to unified → split CPDP migration:** Can the same adoption flow be reused there?

---

## Conventions used across these docs

- **Placeholders.** Where information is unknown or pending input, sections are marked `_TBD_` or wrapped in `> TODO: …` blockquotes. Don't read these as decisions.
- **File:line citations.** Code references use the repo-relative path from `claude_wks/astro_coding_e2e/<repo>/…`, e.g. `houston-api/src/lib/deployments/operator/index.js:728`. Line numbers are accurate as of the date in each doc's header.
- **Codebases referenced.** `astronomer/` (umbrella chart), `houston-api/`, `commander/`, `airflow-operator/`, `apc-ui/`, `astro-cli/`, `apc-airflow/`, `dag-deploy/`.
