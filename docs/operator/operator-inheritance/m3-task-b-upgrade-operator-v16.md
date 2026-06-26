# M3 / Task B — Upgrade the Astro Runtime Operator to v1.6.x / v16.x

**Parent milestone:** [M3 — Stage 2 parity](m3-stage-2-parity.md)
**Linear issue:** _not yet filed_
**Owner:** _TBD (coordinate with Ian — operator team)_
**Effort:** _S–M depending on breaking changes confirmed_
**Priority (from milestone description):** Low standalone; gating for the rest of M3.

> Linked Linear milestone description (verbatim):
> *"Upgrade the operator to v16+: Current APC 0.37.x supports operator version 1.15.6. We need to upgrade the operator version to 16.x. This is a low priority task in this stage as this would mean just bump the operator version (installing latest version of operator). There may not be many breaking changes since this is a minor bump, but we need to confirm this with Ian."*

> **Note on version numbering.** The milestone description references "1.15.6" and "16.x", but the recon of the local repos found image tag `1.5.2` pinned in [`astronomer/charts/airflow-operator/values.yaml`](../../../charts/airflow-operator/values.yaml) and `1.6.0-rc1` referenced in [`../01-codebase-changes.md`](../01-codebase-changes.md). _The exact target version needs confirmation with the operator team_ — this doc uses "v1.6.x / v16.x" placeholder.

---

## Goal

Bump the operator version that APC ships with to the latest stable line. Bring the chart-side CRDs in sync. Verify no behaviour regressions in operator-mode deployments. Decide whether the bump is shipped before or together with M3 / Task A.

## Current state

### What APC ships today

| Artefact | Value | Source |
|---|---|---|
| Pinned operator image tag (APC chart) | `1.5.2` | [`astronomer/charts/airflow-operator/values.yaml`](../../../charts/airflow-operator/values.yaml) |
| Pinned subchart version | `0.1.0` | [`astronomer/charts/airflow-operator/Chart.yaml`](../../../charts/airflow-operator/Chart.yaml) |
| CRD manifests in chart | 14 YAML files | [`astronomer/charts/airflow-operator/templates/crds/`](../../../charts/airflow-operator/templates/crds/) |
| Subchart toggle | `global.airflowOperator.enabled` (default `false`) | [`astronomer/values.yaml:52-55`](../../../values.yaml#L52-L55) |

### Operator repo (`airflow-operator/`)

- `airflow-operator/Makefile:2` — `VERSION ?= 0.0.1` (placeholder; CI auto-updates per the comment at line 1).
- `airflow-operator/helm/Chart.yaml` — both `version` and `appVersion` are `"0.1.0"` (chart-time placeholders, also auto-updated by CI per the comment).
- No `VERSION` file at repo root.
- `airflow-operator/CHANGELOG.md` — structured release notes; uses git-sha-stamped revisions like `main-312b942-1660562381`. **The visible top entries are old (timestamps from 2022).** Suggests the changelog needs refreshing, or releases haven't been logged here lately. _Confirm with Ian what the source of truth is — possibly GitHub Releases instead._
- `airflow-operator/apis/airflow/v1beta1/airflow_types.go` — most recent modification time observed: Apr 6 (per recon).
- CRD source-of-truth: [`airflow-operator/config/crd/bases/`](../../../../airflow-operator/config/crd/bases/) — 13 YAML files (the chart's 14th is the Astronomer-specific `allocator.yaml`).
- API groups present: **only `v1beta1`**. No `v2`, `v2beta1`, or `v1alpha1` CRD groups in the chart or operator.

### Existing per-repo references

[`../01-codebase-changes.md`](../01-codebase-changes.md) §1 (Astronomer Helm Chart, "What Needs To Be Done") flags this directly:
> *"Update operator image tag: Chart has 1.5.2, operator repo has 1.6.0-rc1. Determine which version to ship with APC 2.0. Coordinate with operator team on a stable release."*

[`../03-gap-analysis.md`](../03-gap-analysis.md) Gap 3 covers the same.

## Proposed approach

### Step 1 — Pick a target version

Coordinate with the operator team (Ian) on:

- The stable release line to target.
- Any known breaking changes between `1.5.2` and the target (the milestone description suggests these are minimal but unconfirmed).
- Whether v1.6.x and v16.x refer to the same thing or two different lines.

Capture the decision in an issue comment + ADR-style note appended to this doc.

### Step 2 — Sync CRD YAMLs

Replace the contents of [`astronomer/charts/airflow-operator/templates/crds/`](../../../charts/airflow-operator/templates/crds/) with the manifests from the chosen tag's [`airflow-operator/config/crd/bases/`](../../../../airflow-operator/config/crd/bases/). Pay attention to:

- New fields (e.g. APIServer-related fields if not already present — see [`../03-gap-analysis.md`](../03-gap-analysis.md) Gap 2).
- Renamed/removed fields.
- Validation rule changes (`x-kubernetes-validations`, `pattern`, `enum`).

Generate a diff and review with operator team.

### Step 3 — Bump image tag

[`astronomer/charts/airflow-operator/values.yaml`](../../../charts/airflow-operator/values.yaml):

```yaml
images:
  manager:
    repository: quay.io/astronomer/airflow-operator-controller
    tag: <new-version>          # was 1.5.2
```

Verify the image at the new tag is published to `quay.io/astronomer/`. For air-gapped customers, ensure the image is mirrored to internal registries documented at [`astronomer/values.yaml:29-51`](../../../values.yaml#L29-L51) (private CA / pull-through config).

### Step 4 — Verify Houston compatibility

[`houston-api/src/lib/deployments/operator/index.js`](../../../../houston-api/src/lib/deployments/operator/index.js) (1498 lines) generates the CRD spec. Any new required fields in the upgraded CRD must be:

- Either defaulted by the operator's webhook (preferred), or
- Explicitly emitted by Houston.

Run the integration suite at [`astronomer/docs/operator/02-local-setup.md`](../../02-local-setup.md) against the new operator + existing Houston code. Capture any field-validation errors and decide: fix in Houston (extending [`getCRDSpecFromHelmValues()`](../../../../houston-api/src/lib/deployments/operator/index.js#L728)) or push back to operator team to keep webhook defaults.

If [M3 / Task A](m3-task-a-spec-gen-to-commander.md) is happening in parallel, the same compatibility work happens in Commander instead.

### Step 5 — Run the chart tests

[`astronomer/tests/chart_tests/test_airflow_operator.py`](../../../tests/chart_tests/test_airflow_operator.py) exists per [`../01-codebase-changes.md`](../01-codebase-changes.md) §1. Update test fixtures to match new CRD shapes; add tests for any new fields. _(Use the `chart-tests` skill.)_

### Step 6 — Local-dev guide refresh

[`../02-local-setup.md`](../02-local-setup.md) hardcodes image tag `1.5.2` in two places (the manual-setup values.yaml and the script defaults). Bump both.

### Step 7 — Release notes

Add a short upgrade-notes section to the APC release notes documenting the bump and any customer-facing surface changes.

## Affected files (initial inventory)

| File | Change |
|------|--------|
| [`astronomer/charts/airflow-operator/values.yaml`](../../../charts/airflow-operator/values.yaml) | Bump `images.manager.tag`. |
| [`astronomer/charts/airflow-operator/Chart.yaml`](../../../charts/airflow-operator/Chart.yaml) | Bump chart `version` / `appVersion`. |
| [`astronomer/charts/airflow-operator/templates/crds/*.yaml`](../../../charts/airflow-operator/templates/crds/) | Resync with operator repo's `config/crd/bases/`. |
| [`astronomer/charts/airflow-operator/templates/manager/`](../../../charts/airflow-operator/templates/manager/) | Reconcile if operator's manager deployment shape changed. |
| [`astronomer/charts/airflow-operator/templates/webhooks/`](../../../charts/airflow-operator/templates/webhooks/) | Reconcile if webhook spec changed (paths, failurePolicy). |
| [`astronomer/charts/airflow-operator/templates/rbac/`](../../../charts/airflow-operator/templates/rbac/) | Reconcile if the operator's ClusterRole grew/shrank. |
| [`astronomer/tests/chart_tests/test_airflow_operator.py`](../../../tests/chart_tests/test_airflow_operator.py) | Update fixtures / assertions. |
| [`astronomer/docs/operator/02-local-setup.md`](../../02-local-setup.md) | Bump tag references (lines hardcoded — search for "1.5.2"). |
| [`houston-api/src/lib/deployments/operator/index.js`](../../../../houston-api/src/lib/deployments/operator/index.js) | _Only if_ new required fields appear. |

## Open questions

- [ ] **Target version.** Confirm with Ian: v1.6.x or v16.x? _(See note at top.)_
- [ ] **Breaking changes inventory.** Generate from `git log` between current and target tag in the `airflow-operator` repo. The in-repo `CHANGELOG.md` looks stale.
- [ ] **CRD validation strictness.** New version may reject specs that 1.5.2 accepted. Need a dry-run pass on existing customer CRs (especially M2-adopted ones).
- [ ] **Webhook backward compatibility.** Operator webhooks default missing fields. If a customer pinned APC chart version X (with operator 1.5.2) and we ship X+1 (with operator 1.6.x), in-place upgrade should not require re-emission of CRs.
- [ ] **APIServer / EventScheduler fields.** Are they part of the bump? Affects M3 / Task A and Gap 2.
- [ ] **Conditional ship with Task A.** Ship B in one release, A in the next? Or together? _Coordination call._
- [ ] **Re-emitting specs after the bump.** Do we need a one-shot resync of existing operator-mode deployments? If Houston (or future Commander) starts emitting new fields, in-place reconcile should propagate.

## Out of scope

- Architectural move from Houston to Commander → [Task A](m3-task-a-spec-gen-to-commander.md).
- Closing parity gaps → [Task C](m3-task-c-close-apc-gaps.md), [Task D](m3-task-d-close-operator-gaps.md).

## Acceptance criteria (draft)

- [ ] Operator image tag in chart matches the agreed target version.
- [ ] CRD YAMLs in chart match operator repo at the same tag.
- [ ] All existing chart tests pass.
- [ ] Local-dev guide brings up a cluster with the new operator successfully.
- [ ] End-to-end operator-mode deployment (via [`02-local-setup.md`](../../02-local-setup.md)) creates, runs DAGs, and is deleted without error.
- [ ] An existing APC 0.37.x or 1.x cluster can be upgraded in-place without breaking operator-mode deployments.
- [ ] Release notes drafted.
