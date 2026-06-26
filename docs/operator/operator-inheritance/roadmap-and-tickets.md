# Operator Inheritance — Roadmap, Milestones & Linear ticket plan (DRAFT)

**Status:** Draft for review. Nothing in Linear yet. Discuss → adjust → then push.
**Constraints:** 2 sprints, 1 month (≈4 working weeks). Each sprint must ship something testable.
**Linear project:** [Operator Inheritance](https://linear.app/astronomer/project/operator-inheritance-6426e0c693ab)

The design is settled (see [`00-overview.md`](00-overview.md)). This doc is purely about how to slice the work into Linear *milestones* + *epics* + *tickets* so we can parallelise across teams, keep each sprint demoable, and have a clean prioritisation lever if any track slips.

---

## 1. Milestones (sub-milestones within the Operator Inheritance project)

Within the existing **M2 — [Stage 1 → 2] Astro Runtime operator to APC adoption** Linear milestone, I propose **seven functional sub-milestones**. Each is independently shippable (in the "tests pass + demo runnable" sense), so we can deprioritise / cut without breaking others. Sprint scheduling is layered on top (§ 3).

| # | Milestone | One-line goal | Ships independently? | Sprint target |
|---|---|---|---|---|
| **M2.A** | **DP install + cluster registration** | A customer with a standalone-operator cluster can install the APC DP onto it and register with an existing CP. | Yes | 1 |
| **M2.B** | **Commander: SSA + `GetCustomResource`** | Commander's `ApplyCustomResource` can do server-side apply preserving customer-set fields; new RPC fetches a single CR. | Yes | 1 |
| **M2.C** | **Houston: catalogue map + adoption mutations** | `adoptDeployment` + `unadoptDeployment` mutations work, with a CR → upsert-payload catalogue map and structured incompatibility errors. | Depends on M2.B for live deploys; resolves to stubs otherwise. | 1 (scaffold) + 2 (full) |
| **M2.D** | **Houston: worker branching + soft-delete + isFrozen check** | All deployment-edit workers respect the adopted flag + check `Deployment.isFrozen` before any Commander call. Soft-delete-only for adopted (A.3). SSA path triggered for adopted CRs. | Depends on M2.C and the generic per-deployment freeze ticket (A.1, parallel to operator-inheritance scope) | 2 |
| **M2.E** | **Per-deployment infrastructure handling** | Env vars / metadata DB / registry wired through adoption. Metrics labels checked. Logs **may slip to v1.1** (blocked on ES user creation discovery). | Depends on M2.C + small bits of M2.B | 2 |
| **M2.F** | **CLI surface** | `astro deployment adopt` + `astro deployment unadopt` work end-to-end. | Depends on M2.C | 2 |
| **M2.G** | **Docs + runbook** | Customer-facing adoption runbook and operator-facing rollback runbook are written and reviewed. | Continuous through 1 & 2 |

**Linear milestone names (for filing):**
- `v1 / M2.A — DP install + cluster registration`
- `v1 / M2.B — Commander SSA + GetCustomResource`
- `v1 / M2.C — Houston adoption mutations`
- `v1 / M2.D — Worker branching + rollback flags`
- `v1 / M2.E — Per-deployment infra`
- `v1 / M2.F — CLI surface`
- `v1 / M2.G — Docs + runbook`
- `v1.1 / Follow-ups` — see § 6 *Deferred*

Why not align milestones 1:1 with sprints? Because sprint boundaries are calendar-driven and don't respect engineering team boundaries. Functional milestones let us re-shuffle scope between sprints if (say) Commander finishes M2.B early and Houston is still on M2.C.

---

## 2. Dependency graph

```
                              ┌────────── M2.G (docs) ──────────┐
                              │                                  │
   M2.A (DP install + register)                                   │
                                                                  │
   M2.B (Commander SSA + Get) ────────────┐                       │
                                          ▼                       │
                                M2.C (Houston mutations + catalogue)
                                          │                       │
                                          ▼                       │
                                M2.D (workers + rollback flags) ──┤
                                          │                       │
                                          ▼                       │
                                M2.E (per-deployment infra) ──────┤
                                          │                       │
                                          ▼                       │
                                M2.F (CLI) ───────────────────────┘
```

- **M2.A and M2.B start in parallel on day 1.** Different teams (chart vs Commander).
- **M2.C starts in Sprint 1** with the catalogue-map module (no CP/DP coupling — pure function); waits for M2.B to finish before the resolver can do real `GetCustomResource` calls.
- **M2.D, M2.E, M2.F run in Sprint 2** once M2.C lands.
- **M2.G runs continuously**, owned by whoever wrote the code in the corresponding milestone.

---

## 3. Sprint plan

### Sprint 1 (Weeks 1–2) — Foundation

Three independent tracks; each delivers a demoable artefact.

| Track | Milestone | What lands by end of Sprint 1 |
|---|---|---|
| **Commander** | M2.B | Proto changes shipped. `ApplyCustomResource` SSA path works. `GetCustomResource` returns a CR. Integration test: SSA preserves customer-set fields. |
| **Chart / install** | M2.A | Generator script exists. Survey runs on a k3d cluster with operator pre-installed. `helm upgrade` brings up DP pods. `registerCluster` mutation succeeds. Customer-facing runbook in draft. |
| **Houston** | M2.C (scaffold) | Catalogue map module + unit-test corpus. GraphQL schema for `adoptDeployment` + `unadoptDeployment`. Resolvers wired up against stubs (no real Commander call yet). Both flags wired into config. |

**Sprint 1 demo script (~30 min):**
1. Spin up k3d cluster + standalone operator + a sample `Airflow` CR (use [`examples/production-airflow.yaml`](examples/production-airflow.yaml)).
2. Run the generator script + `helm upgrade` → DP pods come up.
3. Call `registerCluster` → new Cluster row visible.
4. `grpcurl` Commander → `GetCustomResource` returns the CR.
5. `grpcurl` Commander → `ApplyCustomResource` with SSA → only Houston-owned fields change; customer's toleration field survives.
6. Show catalogue-map unit-test green output against the live CR fixture.

### Sprint 2 (Weeks 3–4) — End-to-end

| Track | Milestones | What lands by end of Sprint 2 |
|---|---|---|
| **Houston** | M2.C (full), M2.D, M2.E | `adoptDeployment` resolver does the 13-step flow including real Commander calls. Workers branch on adopted flag + `Deployment.isFrozen`. Soft-delete-only for adopted (A.3). Phase E: env vars (E.1), metadata DB (E.4), registry (E.5), metrics labels (E.3). E.2 logs ships only if 6.9 unblocked. |
| **CLI** | M2.F | `astro deployment adopt` + `astro deployment unadopt` work against the new mutations. |
| **Chart + Docs** | M2.A polish, M2.G | Customer-facing adoption runbook complete. Rollback runbook complete. CI integration on the new DP-install path. |

**Sprint 2 demo script (~30 min):**
1. Re-use the Sprint 1 k3d cluster.
2. `kubectl get airflows -A` → see the CR.
3. `astro deployment adopt --cluster X --workspace Y --namespace N --name M --webserver-url ...` → new Deployment in Astro UI.
4. Edit worker replicas in Astro UI → Houston SSA-patches the CR → customer-set toleration preserved → operator reconciles → an extra worker pod appears.
5. Call `freezeDeployment(deploymentUuid)` → `Deployment.isFrozen=true` → edit replicas again → log shows the worker short-circuited; CR not touched. `unfreezeDeployment` resumes.
6. Flip back → resume.
7. `astro deployment unadopt` → Houston row soft-deleted; CR + namespace + pods untouched (`kubectl get pods -n N` shows everything still running).
8. Compatibility-error demo: adopt a CR with `airflowPlugins[]` (no Houston column) → CLI shows structured error → re-run with `--accept-incompatibilities` → succeeds, plugin info stashed in `config.adoption.rawCRSnapshot`.

---

## 4. Epics + tickets

Each Epic maps to one milestone. Ticket IDs are local (e.g. `1.3`); they'll become Linear issue IDs once filed.

Estimation key: **XS** (<1d), **S** (1–2d), **M** (3–5d), **L** (1–2w), **XL** (>2w — red flag).

Priority: **P0** must-ship, **P1** should-ship, **P2** nice-to-have, **P3** stretch.

---

### Epic 1 — Commander SSA + `GetCustomResource` RPC
**Milestone:** M2.B
**Owner team:** Commander team — _owner TBD_
**Sprint:** 1

#### 1.1 — Add `field_manager` + `force_apply` to `ApplyCustomResourceRequest` proto
- **Description:** Extend [`commander/_proto/custom_resource.proto`](../../../../commander/_proto/custom_resource.proto) with `string field_manager = 17` and `bool force_apply = 18` on the existing `ApplyCustomResourceRequest`. Regenerate Go bindings.
- **Acceptance criteria:**
  - New proto fields land + bindings regenerated.
  - Backward-compatible: when unset, no behaviour change.
  - `grpc-readme-updater` skill run to update README.
- **Est:** XS · **Priority:** P0 · **Depends on:** —

#### 1.2 — Define `GetCustomResource` RPC
- **Description:** Add a new RPC to [`commander/_proto/commander.proto`](../../../../commander/_proto/commander.proto): `rpc GetCustomResource(GetCustomResourceRequest) returns (GetCustomResourceResponse)`. Request carries `(group, version, plural, namespace, name)`; response carries the full unstructured spec (as JSON string) + metadata.
- **Acceptance criteria:**
  - Proto defined and bindings regenerated.
  - `grpc-readme-updater` skill run.
- **Est:** XS · **Priority:** P0 · **Depends on:** —

#### 1.3 — Implement `ApplyCustomResource` SSA path
- **Description:** Modify [`commander/kubernetes/custom_resource.go`](../../../../commander/kubernetes/custom_resource.go). When `field_manager` is set on the request, switch from `Update()` to `Patch(types.ApplyPatchType, ..., FieldManager: <value>, Force: force_apply)`. Preserve existing `Create`-or-`Update` semantics when `field_manager` is unset.
- **Acceptance criteria:**
  - Existing tests still pass.
  - New unit test: with `field_manager` set, dynamic-client is called with `Patch(ApplyPatchType)`.
  - 409 conflict on field collision is returned to the caller with a clear error.
- **Est:** M · **Priority:** P0 · **Depends on:** 1.1

#### 1.4 — Implement `GetCustomResource` handler
- **Description:** Add handler in [`commander/api/custom_resource.go`](../../../../commander/api/custom_resource.go). Delegate to a new `provisioner.GetCustomResource(in)` method that calls the dynamic client's `Get()`.
- **Acceptance criteria:**
  - RPC returns the CR spec + metadata as JSON string.
  - Not-found returns a clean gRPC NotFound status.
- **Est:** S · **Priority:** P0 · **Depends on:** 1.2

#### 1.5 — Unit tests for SSA + Get
- **Description:** Go unit tests with a fake dynamic client. Cover: (a) SSA applies the patch with the right manager + force flag, (b) Get returns the right object, (c) error paths.
- **Est:** S · **Priority:** P0 · **Depends on:** 1.3, 1.4

#### 1.6 — Integration test: SSA preserves customer-set fields
- **Description:** New scenario under `commander/integration-tests/`. Pre-create an `Airflow` CR with a non-Astronomer field (e.g. `spec.workers[0].podTemplateSpec.spec.tolerations[]` with a custom key). Call `ApplyCustomResource` with `field_manager=apc-commander` and a slim spec that doesn't include the toleration. Assert: the toleration is still present on the CR after the patch.
- **Acceptance criteria:**
  - Test green on a k3d cluster with cert-manager + operator installed.
  - Test fails if SSA path is removed.
- **Est:** M · **Priority:** P0 · **Depends on:** 1.3

---

### Epic 2 — Houston catalogue map (CR → upsert payload)
**Milestone:** M2.C
**Owner team:** Houston team — _owner TBD_
**Sprint:** 1

#### 2.1 — New `cr-to-deployment.ts` module
- **Description:** Create `houston-api/src/lib/deployments/operator/cr-to-deployment.ts`. Export a pure function `crToDeployment(crSpec, namespaceLabels, secrets): { upsertInput, compatibility }`. Implement the mapping table from [`reference-cr-mapping-walkthrough.md`](reference-cr-mapping-walkthrough.md).
- **Acceptance criteria:**
  - Function is pure (no I/O).
  - Returns `{ upsertInput: AdoptDeploymentInputResolver, compatibility: { compatible[], partial[], incompatible[] } }`.
- **Est:** M · **Priority:** P0 · **Depends on:** —

#### 2.2 — Compatibility report for unmapped fields
- **Description:** Within `cr-to-deployment.ts`, walk every top-level CR field and classify as `compatible | partial | incompatible`. Examples: `spec.airflowPlugins[]` → incompatible; `spec.podTemplateConfigMapName` → incompatible; multiple worker groups → partial (first goes to first-class column, extras → `config.adoption.workerGroupsOverflow`).
- **Acceptance criteria:**
  - Compatibility list is deterministic per fixture input.
  - Each entry carries `{ path, reason }`.
- **Est:** S · **Priority:** P0 · **Depends on:** 2.1

#### 2.3 — Special case: AF 3.x runtime with `spec.webserver` (no `apiServer`)
- **Description:** Detect runtime version `>=13.x` with `spec.webserver` present and `spec.apiServer` absent (the 0.37-emitted-AF-3.x quirk from the walkthrough). Set `Deployment.config.adoption.specQuirks.airflow3xUsingWebserver = true`.
- **Est:** S · **Priority:** P0 · **Depends on:** 2.1

#### 2.4 — Special case: re-adopted APC-emitted CR
- **Description:** Detect `AIRFLOW__ASTRONOMER__HOUSTON_JWK_URL` env var present in `spec.env`. Compare its host against the current Houston's URL. If different, surface as a `partial` incompatibility (requires the future `migrateAirflowAuth` mutation to fully resolve).
- **Est:** S · **Priority:** P1 · **Depends on:** 2.1, 2.2

#### 2.5 — Workspace recovery from namespace label
- **Description:** Add a helper that reads `namespace.metadata.labels.workspace` (from the catalogue input). Resolver uses it as a hint when the operator hasn't supplied a `workspaceUuid`. Not authoritative — operator can override.
- **Est:** XS · **Priority:** P0 · **Depends on:** 2.1

#### 2.6 — Collect env-var Secret names from CR
- **Description:** Walk `spec.env[]` (and per-component `env[]`) for `valueFrom.secretKeyRef.name`. Collect the unique set into `config.adoption.envSecretNames: string[]`. Foundation for Epic 6 / E.1.
- **Est:** S · **Priority:** P0 · **Depends on:** 2.1

#### 2.7 — Unit-test fixtures
- **Description:** Build fixtures for: (a) the live 0.37 CR from the walkthrough doc, (b) a hand-written FAB-DB Airflow CR, (c) an AstroExecutor CR with `apiServer`, (d) a CR with custom `airflowPlugins[]` (incompatibility test), (e) a CR with multiple worker groups (partial test). Snapshot tests for the upsert payload + compatibility report.
- **Est:** M · **Priority:** P0 · **Depends on:** 2.1–2.6

---

### Epic 3 — Houston adoption mutations
**Milestone:** M2.C
**Owner team:** Houston team — _owner TBD_
**Sprint:** 1 (scaffold) + 2 (resolver)

#### 3.1 — `OPERATOR_INHERITANCE_ENABLED` env flag
- **Description:** Add to [`houston-api/src/lib/config/`](../../../../houston-api/src/lib/config/) and the houston-configmap template. Default `false`. Surface in Houston's runtime config.
- **Acceptance criteria:** Flag readable via `config.get("operatorInheritance.enabled")`. Chart test confirms it renders.
- **Est:** XS · **Priority:** P0 · **Depends on:** —

#### 3.2 — Per-deployment `Deployment.isFrozen` + `freezeDeployment` / `unfreezeDeployment` mutations (A.1)
- **Description:** Add a Prisma migration adding `isFrozen: Boolean @default(false)` to `Deployment`. Add two new mutations in [`houston-api/src/schema/mutation.js`](../../../../houston-api/src/schema/mutation.js): `freezeDeployment(deploymentUuid: ID!, reason: String): Deployment!` and `unfreezeDeployment(deploymentUuid: ID!): Deployment!`. Resolver toggles the column and writes an audit-log entry. **Generic across modes** (helm + operator + adopted) — files outside operator-inheritance scope as a standalone capability. Workers consume the flag (Epic 4).
- **Est:** S · **Priority:** P0 · **Depends on:** —

#### 3.3 — `adoptDeployment` mutation schema
- **Description:** Add to [`houston-api/src/schema/mutation.js`](../../../../houston-api/src/schema/mutation.js). Input per [`m2-task-3` § Phase C](m2-task-3-migrate-deployments-to-cp.md#phase-c--adopt): `workspaceUuid`, `clusterId`, `crNamespace`, `crName`, `label?`, `description?`, `useApcLogging?`, `useApcMetrics?`, `useApcRegistry?`, `acceptIncompatibilities?` (default true). Return type `Deployment!`.
- **Est:** S · **Priority:** P0 · **Depends on:** —

#### 3.4 — `adoptDeployment` resolver (full 11-step flow)
- **Full ticket spec:** [`tickets/adopt-deployment-mutation.md`](tickets/adopt-deployment-mutation.md)
- **Team:** PLX. Permissions + request/response shapes + 13 acceptance criteria fleshed out there.
- **Est:** L · **Priority:** P0 · **Depends on:** 2.x, 3.1, 3.3, 3.7

#### 3.5 — `unadoptDeployment` mutation schema
- **Description:** Add to [`houston-api/src/schema/mutation.js`](../../../../houston-api/src/schema/mutation.js). Input: `deploymentUuid: ID!`. Return type `Deployment!`.
- **Est:** XS · **Priority:** P0 · **Depends on:** —

#### 3.6 — `unadoptDeployment` resolver
- **Description:** Implement `houston-api/src/resolvers/mutation/unadopt-deployment/index.ts`. Per § Phase F: validate the deployment exists and is adopted, **do not publish any worker event**, soft-delete the row (`deletedAt = now()`), delete deployment-scoped `RoleBinding`s, audit-log. No K8s touch.
- **Acceptance criteria:**
  - Returns the deployment with `deletedAt` set.
  - `RoleBinding`s with `deploymentId = ?` removed.
  - Workspace + invited users untouched.
  - Verify zero K8s API calls during the resolver (mock Commander).
- **Est:** S · **Priority:** P0 · **Depends on:** 3.5

#### 3.7 — `GetCustomResource` gRPC client wrapper in Houston
- **Description:** Add a thin TypeScript wrapper around the commander gRPC client to call `GetCustomResource(clusterId, group, version, plural, namespace, name)`. Houston uses the existing commander stub setup; just expose the new method.
- **Est:** S · **Priority:** P0 · **Depends on:** 1.4

#### 3.8 — Flag enforcement in mutations
- **Description:** Both `adoptDeployment` and `unadoptDeployment` reject when `OPERATOR_INHERITANCE_ENABLED=false` with a clear error message.
- **Est:** XS · **Priority:** P0 · **Depends on:** 3.1, 3.4, 3.6

#### 3.9 — Audit-log entries for adopt + un-adopt
- **Description:** Reuse the existing Houston audit-log helpers. Entry fields: `action ∈ {"adopt","unadopt"}`, `userId`, `deploymentId`, `releaseName`, `namespace`, optional `incompatibilitiesAccepted` boolean.
- **Est:** XS · **Priority:** P0 · **Depends on:** 3.4, 3.6

#### 3.10 — Unit + integration tests
- **Description:** Jest unit tests for both resolvers (mocking Commander + Prisma). One integration test that runs both mutations against a real Houston + a mocked Commander + a real Postgres.
- **Est:** M · **Priority:** P0 · **Depends on:** 3.4, 3.6

---

### Epic 4 — Worker branching + `isFrozen` enforcement + adopted soft-delete
**Milestone:** M2.D
**Owner team:** Houston team — _owner TBD_
**Sprint:** 2
**Depends on:** Epic 3, Epic 1

#### 4.1 — `deployment-upserted-for-create` worker: adoption branch
- **Description:** In [`houston-api/src/workers/deployment-upserted-for-create/index.js`](../../../../houston-api/src/workers/deployment-upserted-for-create/index.js), branch on `deployment.config.adoption.adopted === true`. When true, call `commander.request("ApplyCustomResource", { ..., field_manager: "apc-commander", force_apply: false })` with the narrowed spec (only fields APC owns).
- **Est:** S · **Priority:** P0 · **Depends on:** 1.1, 3.4

#### 4.2 — `deployment-upserted-for-update` worker
- **Description:** Same change in [`deployment-upserted-for-update/index.js`](../../../../houston-api/src/workers/deployment-upserted-for-update/index.js).
- **Est:** S · **Priority:** P0 · **Depends on:** 4.1

#### 4.3 — `deployment-image-update` worker
- **Description:** Same change in `deployment-image-update/index.js`.
- **Est:** S · **Priority:** P0 · **Depends on:** 4.1

#### 4.4 — `deployment-variables-updated` worker: writeback to customer Secret(s)
- **Description:** When the deployment is adopted, write env-var Secret updates to the names listed in `config.adoption.envSecretNames` instead of `<releaseName>-env`. Multiple Secrets allowed.
- **Acceptance criteria:**
  - Edits via Houston UI on env vars land in the correct customer-named Secret(s).
  - If `envSecretNames` is empty, fall back to the standard `<releaseName>-env` (e.g. for re-adopted APC-emitted CRs).
- **Est:** M · **Priority:** P0 · **Depends on:** 4.1, 6.1

#### 4.5 — Universal `isFrozen` short-circuit on all workers (A.1)
- **Description:** Before any Commander call, every worker checks `deployment.isFrozen === true`. If true, log and return without calling Commander — regardless of mode (helm / vanilla operator / adopted operator). Includes `deployment-deleted` worker's Commander call (the Houston-side row update still proceeds; only the K8s call is gated).
- **Est:** S · **Priority:** P0 · **Depends on:** 3.2, 4.1–4.4

#### 4.6 — Integration test: SSA preserves customer-set fields on edit
- **Description:** End-to-end via a real Houston + Commander + k3d. Pre-create a CR with a custom toleration. Adopt it. Edit worker replicas via Houston. Assert: new pod count matches and the toleration is still on the CR.
- **Est:** M · **Priority:** P0 · **Depends on:** 4.1, 1.6

#### 4.7 — Integration test: `isFrozen` halts every Commander call
- **Description:** Call `freezeDeployment(deploymentUuid)` → assert `Deployment.isFrozen=true`. Trigger updates on the deployment from all five workers (via the GraphQL surfaces that fan out to them). Assert: zero Commander calls during the freeze. Call `unfreezeDeployment` and assert normal operation resumes.
- **Est:** S · **Priority:** P0 · **Depends on:** 4.5

---

### Epic 5 — DP install + cluster registration
**Milestone:** M2.A
**Owner team:** Chart team / APC team — _owner TBD_
**Sprint:** 1

#### 5.1 — Subchart-install gating
- **Description:** Currently `global.airflowOperator.enabled` controls both feature-awareness in Houston/Commander AND the install of the `airflow-operator` subchart. Decouple: introduce `airflow-operator.enabled` (subchart toggle, default `true`) so customers with pre-installed operators can set it to `false` while keeping `global.airflowOperator.enabled=true`. Update [`astronomer/charts/airflow-operator/values.yaml`](../../../charts/airflow-operator/values.yaml) and the umbrella `Chart.yaml` condition.
- **Acceptance criteria:**
  - Chart test confirms subchart skipped when `airflow-operator.enabled=false`.
  - Existing default behaviour preserved.
- **Est:** S · **Priority:** P0 · **Depends on:** —

#### 5.2 — Generator script for DP-onto-operator install
- **Description:** New script at `astronomer/bin/setup-operator-dp.py` (or rename if convention). Inputs: target cluster kubeconfig + context, existing CP `baseDomain`, registry pull credentials. Output: a `values.yaml` ready for `helm upgrade --install`.
- **Acceptance criteria:**
  - Script runs `kubectl` survey before generating.
  - Emits clear error if prerequisites missing (cert-manager, operator).
  - Output values are linted + helm-template'd to no errors.
- **Est:** M · **Priority:** P0 · **Depends on:** 5.1

#### 5.3 — Cluster survey logic
- **Description:** Inside 5.2 (or as a callable submodule), detect: operator install (controller-manager, CRDs), cert-manager, prometheus-operator presence, existing Airflow CRs (count + namespaces), observability stack hints (existing Prometheus / Vector / Fluent-bit DaemonSets), `customLogging.enabled` indicators.
- **Acceptance criteria:**
  - Prints a structured survey report.
  - Refuses to generate values if operator missing OR cert-manager missing.
- **Est:** M · **Priority:** P0 · **Depends on:** 5.2

#### 5.4 — `baseDomain` equality check
- **Description:** Before generating values, the script confirms the supplied DP `baseDomain` matches the CP's `helm.baseDomain` (operator supplies it). Hard fail if not equal.
- **Est:** S · **Priority:** P0 · **Depends on:** 5.2

#### 5.5 — `registerCluster` runbook step
- **Description:** Script prints the exact `registerCluster` GraphQL mutation invocation (including the computed `metadataUrl`) after the install completes. Operator runs it manually (no auto-call in v1; need CP admin token).
- **Acceptance criteria:**
  - Runbook documents the call.
  - Sample command is copy-pasteable.
- **Est:** S · **Priority:** P0 · **Depends on:** 5.2

#### 5.6 — E2E test: install operator on k3d, install DP, register
- **Description:** New CircleCI scenario (use `circleci` and `functional-tests` skills). Steps: create k3d cluster → install standalone operator → install DP via the generator script → call `registerCluster` → assert Cluster row.
- **Est:** L · **Priority:** P0 · **Depends on:** 5.2, 5.5

#### 5.7 — Customer-facing install runbook
- **Description:** Markdown doc under `astronomer/docs/operator/operator-inheritance/` (e.g. `runbook-install.md`). Step-by-step: prerequisites, cert-manager check, generator-script invocation, helm upgrade, registerCluster, troubleshooting.
- **Est:** M · **Priority:** P1 · **Depends on:** 5.2

#### 5.8 — cert-manager coexistence test
- **Description:** What if the customer's cert-manager is older / different version than what APC's chart expects? Add a chart test confirming the install doesn't conflict + document compatible version range.
- **Est:** S · **Priority:** P1 · **Depends on:** 5.2

---

### Epic 6 — Per-deployment infrastructure handling (Phase E)
**Milestone:** M2.E
**Owner team:** Houston team — _owner TBD_
**Sprint:** 2
**Depends on:** Epic 3, Epic 1

#### 6.1 — E.1 Env vars: read via Commander, store secret names
- **Description:** Inside the `adoptDeployment` resolver (3.4), after the catalogue map collects `envSecretNames`, call `Commander.GetSecret` for each name → populate `Deployment.environmentVariables` with `{ name, value, isSecret: true, sourceSecret: <name> }`. Persist `config.adoption.envSecretNames`.
- **Est:** M · **Priority:** P0 · **Depends on:** 3.4, 2.6

#### 6.2 — E.1 Env vars: writeback to customer-named Secret(s) on edits
- **Description:** See 4.4. The worker resolves the target Secret name from `config.adoption.envSecretNames` and writes there. Add `Commander.SetSecret` calls accordingly.
- **Est:** M · **Priority:** P0 · **Depends on:** 6.1, 4.4

#### 6.3 — E.1 External secret-manager detection (read-only mode)
- **Description:** When reading a customer-named Secret via Commander, check for owner references to `ExternalSecret`, `SealedSecret`, `VaultSecret`, or annotations like `external-secrets.io/managed-by`. If detected, mark all env vars from that Secret as `readOnly: true` and store the detection result in `config.adoption.envSecretNamesExternal[]`. UI surfaces the lock icon. Edits via Houston are rejected with `code="ENV_VAR_EXTERNALLY_MANAGED"`.
- **Acceptance criteria:**
  - Detection covers ExternalSecretsOperator (most common).
  - Edit attempt returns structured error.
- **Est:** M · **Priority:** P1 · **Depends on:** 6.1, 6.2 · **Deferrable** to v1.1 if Sprint 2 is tight.

#### 6.4 — E.4 Metadata DB: read connection + populate `airflowDbRef`
- **Description:** Inside 3.4, call `Commander.GetSecret(crNamespace, spec.secrets.metadataSecretName)` → extract connection URI → populate `Deployment.airflowDbRef.activeConnectionRef`. Same for result backend.
- **Est:** S · **Priority:** P0 · **Depends on:** 3.4

#### 6.5 — E.4 Fernet key + SSL settings preservation
- **Description:** Copy `spec.useExternallyManagedFernetKey`, `spec.databaseSSLMode`, `spec.databaseSSLSecretName` from the CR into `Deployment.config.database.*`. APC respects these; no rotation.
- **Est:** S · **Priority:** P0 · **Depends on:** 6.4

#### 6.6 — E.5 Registry: record customer's image + imagePullSecret
- **Description:** Copy `spec.image` + `spec.imagePullSecret` into `Deployment.config.adoption.registry = { image, imagePullSecret }`. Do not generate a new registry password.
- **Est:** S · **Priority:** P0 · **Depends on:** 3.4

#### 6.7 — E.5 Special case: APC-emitted CR already on APC's registry
- **Description:** If `spec.image` hostname matches the new CP's registry hostname (e.g. `registry.<helm.baseDomain>`), generate a registry password tied to the new CP and SSA-patch the `dockerconfigjson` Secret. Detection logic + the SSA call.
- **Est:** M · **Priority:** P1 · **Depends on:** 6.6

#### 6.8 — E.3 Metrics: scrape label verification + SSA patch
- **Description:** During the catalogue map, check each component's `customLabels` and `podTemplateSpec.metadata.labels` for the expected scrape labels (`astronomer.io/platform-release` etc. — confirmed in walkthrough). If missing, append to the SSA patch that adoption applies.
- **Est:** S · **Priority:** P0 · **Depends on:** 2.1

#### 6.9 — E.2 Logs: investigate ES user creation flow for native deployments
- **Description:** **Research ticket — blocker for 6.10.** Confirm where the per-deployment ES user/role is created today. Possibilities: an ES init job in the chart, an ES sidecar, an admin-API call from Houston, or somewhere else entirely. Time-box to 1 working day at the start of Sprint 1.
- **Acceptance criteria:**
  - Documented finding in `m2-task-3` § E.2.
  - Decision: ship E.2 in Sprint 2 vs defer to v1.1.
- **Est:** S · **Priority:** P0 · **Depends on:** —

#### 6.10 — E.2 Logs: ES user provisioning + CR env var SSA patch
- **Description:** Once 6.9 unblocks, implement the actual ES user creation path for adopted deployments + SSA-patch the CR's `AIRFLOW__ELASTICSEARCH__HOST` / `..._ELASTICSEARCH_HOST` to point at the new Secret. **Likely to slip to v1.1** if 6.9 reveals it's non-trivial.
- **Est:** M (if path is clean) — XL (if it requires touching ES chart / multi-team) · **Priority:** P0 with caveat · **Depends on:** 6.9, 6.4

---

### Epic 7 — Astro CLI
**Milestone:** M2.F
**Owner team:** CLI team — _owner TBD_
**Sprint:** 2

#### 7.1 — `astro deployment adopt` subcommand
- **Description:** New subcommand in [`astro-cli/cmd/software/deployment.go`](../../../../astro-cli/cmd/software/deployment.go) near `newDeploymentCreateCmd` (line ~141). Flags: `--cluster`, `--workspace`, `--namespace`, `--name`, `--label`, `--description`, `--webserver-url`, `--accept-incompatibilities`. Calls the `adoptDeployment` mutation.
- **Acceptance criteria:**
  - All flags wired.
  - Successful adoption prints the new deployment ID + URL.
  - Failure on `OPERATOR_INHERITANCE_ENABLED=false` prints the GraphQL error clearly.
- **Est:** M · **Priority:** P0 · **Depends on:** 3.3, 3.4

#### 7.2 — `astro deployment unadopt` subcommand
- **Description:** Single `--deployment` flag. Calls the `unadoptDeployment` mutation. Confirms before proceeding (interactive prompt unless `--yes`).
- **Est:** S · **Priority:** P0 · **Depends on:** 3.5, 3.6

#### 7.3 — Structured incompatibility error → friendly CLI output
- **Description:** When the mutation returns `extensions.code="ADOPTION_INCOMPATIBLE"`, parse `extensions.incompatibleFields` and print a readable table. Suggest the `--accept-incompatibilities` flag for the re-run.
- **Est:** S · **Priority:** P0 · **Depends on:** 7.1

#### 7.4 — CLI tests
- **Description:** Unit + integration tests for both subcommands. Mock the Houston GraphQL endpoint.
- **Est:** S · **Priority:** P0 · **Depends on:** 7.1, 7.2

#### 7.5 — Help text + examples + man-page updates
- **Description:** `astro deployment adopt --help` shows clear examples covering: minimal invocation, with `--webserver-url`, with `--accept-incompatibilities`.
- **Est:** XS · **Priority:** P1 · **Depends on:** 7.1, 7.2

---

### Epic 8 — Astro UI adopt wizard (optional)
**Milestone:** M2.F (stretch) or v1.1
**Owner team:** UI team — _owner TBD_
**Sprint:** 2 if capacity, otherwise v1.1
**Priority:** P2 — CLI is sufficient for the pilot
**Depends on:** Epic 3

#### 8.1 — "Adopt existing deployment" entry point on the deployments page
- **Est:** M · **Priority:** P2 · **Depends on:** 3.4

#### 8.2 — Wizard steps: input identity → preview catalogue-map → fill workspace + URL → confirm
- **Description:** Multi-step React flow. Calls a future `previewAdoption` query (or just calls `adoptDeployment` and parses the structured error to preview). Decide v1 strategy.
- **Est:** L · **Priority:** P2 · **Depends on:** 8.1

#### 8.3 — Adopted badge on deployment list/detail pages
- **Description:** Read `config.adoption.adopted` on every deployment and render a badge in the UI.
- **Est:** S · **Priority:** P2 · **Depends on:** 3.4

#### 8.4 — "Open Airflow" link respects `config.adoption.urls.webserver`
- **Description:** When opening the deployment URL, prefer the override if present. Cross-link with Task 1 § URL handling.
- **Est:** S · **Priority:** P2 · **Depends on:** 3.4

#### 8.5 — E2E tests for the wizard
- **Est:** M · **Priority:** P2 · **Depends on:** 8.1–8.4

---

### Epic 9 — Documentation + runbooks
**Milestone:** M2.G
**Owner team:** Cross-team (engineer-authored, docs-team-edited)
**Sprint:** Continuous through 1 and 2

#### 9.1 — Customer-facing adoption runbook
- **Description:** New markdown doc `astronomer/docs/operator/operator-inheritance/runbook-customer-adoption.md`. End-to-end customer journey: prerequisites → DP install → registerCluster → per-CR adoption.
- **Est:** M · **Priority:** P0 · **Depends on:** 5.7, 7.1

#### 9.2 — Operator-facing rollback runbook
- **Description:** New markdown doc `astronomer/docs/operator/operator-inheritance/runbook-rollback.md`. Covers `freezeDeployment` / `unfreezeDeployment` flow, unadopt procedure, Commander rollback procedure.
- **Est:** S · **Priority:** P0 · **Depends on:** 3.6, 4.5

#### 9.3 — Update `astronomer/docs/operator/02-local-setup.md` for the new adoption flow
- **Description:** Reference the adoption flow + the example CR in `examples/production-airflow.yaml`.
- **Est:** S · **Priority:** P1 · **Depends on:** 9.1

#### 9.4 — CRD field-mapping reference (customer-doc-ready)
- **Description:** Extract the catalogue-mapping table from `reference-cr-mapping-walkthrough.md` into a customer-facing reference.
- **Est:** S · **Priority:** P2 · **Depends on:** 2.1

---

## 5. What ships at the end of each sprint (recap)

**Sprint 1:**
- M2.A complete + tested on k3d.
- M2.B complete + SSA integration test green.
- M2.C scaffolded — catalogue map + unit tests green; resolver returns stub data.

**Sprint 2:**
- M2.C complete — resolver does the full 11-step flow.
- M2.D complete — workers branch correctly; `isFrozen` halts edits; `deleteDeployment` on adopted deployments is soft-delete only.
- M2.E mostly complete — E.1, E.4, E.5, E.3 ship; E.2 ships if 6.9 unblocks.
- M2.F complete — CLI works end-to-end.
- M2.G complete — runbooks written.

---

## 6. Deferred / v1.1 follow-ups (NOT in this month)

| Item | Origin | Why deferred |
|---|---|---|
| **D.2 — Bulk Airflow user import on adoption** | [`m2-task-3` § D.2](m2-task-3-migrate-deployments-to-cp.md#d2--optional-bulk-user-import-new-input-on-adoptdeployment) | Product hasn't confirmed it's wanted for v1. Caveats around SSO-backed Airflow + cross-plane DB reachability. |
| **D.3 Option B — `migrateAirflowAuth` mutation** | [`m2-task-3` § D.3](m2-task-3-migrate-deployments-to-cp.md#d3--airflow-auth-on-adopted-deployments--three-options) | Option A (leave alone) is the v1 default. Option B ships only if pilot customer asks for SSO. |
| **E.2 — Historical log migration from customer's ES** | [`m2-task-3` § E.2](m2-task-3-migrate-deployments-to-cp.md#e2--logs) | Heavy ETL operation. v1 ships post-adoption logs only. |
| **E.2 — Per-deployment ES user provisioning** | Same | Blocked on 6.9 (research). May ship in v1 if path is clean; else v1.1. |
| **E.1 — External-secret-manager handling (read-only enforcement)** | Same § E.1 | If not done in v1, env-var edits get silently reconciled away. Documented as a known limitation. |
| **Astro UI adopt wizard (Epic 8)** | This doc | CLI sufficient for pilot. |
| **`ListCustomResources` RPC for UI bulk discovery** | [`m2-task-2` § Discovery](m2-task-2-connect-operator-to-commander.md#discovery--association) | Operator uses `kubectl get airflows -A`. Revisit only if customer feedback warrants. |
| **Custom log/metric pattern overrides per deployment** | [`m2-task-3` § E.2/E.3](m2-task-3-migrate-deployments-to-cp.md#e2--logs) | v1 requires uniformity. |
| **Migrate metadata DB to APC-managed Postgres** | [`m2-task-3` § E.4](m2-task-3-migrate-deployments-to-cp.md#e4--airflow-metadata-db) | Customers keep their existing DB in v1. |

All of these go into a Linear milestone `v1.1 / Follow-ups` so they stay visible without cluttering sprint planning.

---

## 7. Open questions before pushing to Linear

- [ ] **Sprint calendar alignment.** Which calendar weeks are Sprint 1 and Sprint 2? Cycles in Linear need exact start/end dates.
- [ ] **Pilot customer.** Deutsche Bank vs BofA vs StanChart? Affects Sprint 2 demo: do we demo against the pilot's staging cluster or our own k3d?
- [ ] **Linear project structure.** Sub-milestones inside the existing **Operator Inheritance** project, or a fresh "Operator Inheritance v1" sibling project? Recommend the former.
- [ ] **Epic-as-parent-issue convention.** Linear supports parent / sub-issue. Should each Epic be a parent issue with tickets as children, or just a label/grouping?
- [ ] **Epic ownership.** Names against each Epic:
  - Epic 1 (Commander SSA + Get) — _TBD_
  - Epic 2 (Catalogue map) — _TBD_
  - Epic 3 (Adoption mutations) — _TBD_
  - Epic 4 (Worker branching + flags) — _TBD_
  - Epic 5 (Chart / install) — _TBD_
  - Epic 6 (Per-deployment infra) — _TBD_
  - Epic 7 (CLI) — _TBD_
  - Epic 8 (UI, optional) — _TBD_
  - Epic 9 (Docs) — _TBD_
- [ ] **Ticket 6.9 owner.** The ES-user-creation research ticket. Houston team lead, ideally. Time-boxed to 1 day.
- [ ] **Code-freeze convention.** Are there blackout days for CP/DP releases in this month? Affects what we can ship in Sprint 2.

---

## 8. What happens after this doc is approved

1. Resolve the *Open questions* above with the relevant owners.
2. File the 7 sub-milestones (M2.A through M2.G) + a `v1.1 / Follow-ups` milestone under the existing **Operator Inheritance** project in Linear.
3. For each Epic, file a parent Linear issue under its milestone. Use the Epic name as the title.
4. For each ticket (1.1, 1.2, …), file a child issue under its Epic with the description + acceptance criteria from this doc.
5. Assign owners and target sprints (Linear cycles aligned with Sprint 1 / Sprint 2).
6. Move deferred items into the `v1.1 / Follow-ups` milestone.
7. Pin this doc as the source-of-truth in the project description until the work lands.

---

## Estimation key

| Size | Meaning |
|---|---|
| XS | < 1 day |
| S | 1–2 days |
| M | 3–5 days |
| L | 1–2 weeks |
| XL | > 2 weeks (red flag — split it) |

## Priority key

| Priority | Meaning |
|---|---|
| P0 | Must ship this month |
| P1 | Should ship — drop only if forced |
| P2 | Nice-to-have — CLI/docs-grade quality |
| P3 | Stretch — bonus if there's slack |
