# Design Review — Action Items & Decisions

**Meeting:** Operator Inheritance design walkthrough
**Attendees:** Karan, Rishab, Vishnu, Srini, Pyush (+ others)
**Status:** Summarised from transcript. Review → approve → I apply the changes to the design docs (GitHub + Notion).

This file is the inbox between the meeting and the doc updates. **Nothing in the design docs has changed yet** based on this transcript.

---

## A. Decisions changed — doc updates needed

These overrule what the design docs currently say.

### A.1 — `OPERATOR_INHERITANCE_FREEZE_EDITS` becomes a per-deployment flag, not install-wide

**Old:** Two install-wide flags (`OPERATOR_INHERITANCE_ENABLED` + `OPERATOR_INHERITANCE_FREEZE_EDITS`).
**New (Vishnu):** Per-deployment freeze, **generic across modes** (helm, vanilla operator, adopted operator). E.g. a `Deployment.isFrozen` (or similar) field. When true, all edits to that deployment are blocked.

Rationale: out of 10 deployments, only 1 might be problematic — no reason to freeze the other 9. Also useful for helm-mode debugging, not just adoption.

**Impact:** Drop the install-wide freeze flag. Replace with a per-deployment field. Expose a `freezeDeployment` / `unfreezeDeployment` mutation. The `OPERATOR_INHERITANCE_ENABLED` install-wide flag stays.

### A.2 — `acceptIncompatibilities` defaults to `true`

**Old:** Defaults to `false` (strict rejection unless explicitly opted in).
**New (in-meeting consensus):** Defaults to `true` (always persist what we don't recognise into `config.adoption.rawCRSnapshot`).

Rationale: we don't yet know every CR field we can / can't represent. v1 is permissive; tighten later.

**Impact:** Flip the default in the GraphQL input + resolver + ticket spec.

### A.3 — Deletion is **always soft-delete** for adopted deployments

**Old:** `deleteDeployment` runs the standard destructive path (deletes CR + namespace) even for adopted CRs.
**New (Vishnu):** Hard-delete is dangerous when APC doesn't own the underlying deployment — customer might want to re-fix and re-adopt. **All deletes on adopted deployments are soft-deletes.** Houston row gets `deletedAt`; K8s state is left alone.

Rationale: re-adoption flow needs the customer's CR to still exist; if Houston (or anyone) hard-deletes it, the customer's pods are gone.

**Impact:** Update Task 3 § Phase F (rollback/un-adopt). The `deleteDeployment vs unadoptDeployment` distinction collapses partially — both end up as soft-deletes for adopted CRs. May want a single `unadoptDeployment` mutation only, with `deleteDeployment` either rejected on adopted deployments OR redirected to soft-delete + the standard message.

### A.4 — Bulk user import becomes a separate, second mutation (`adoptDeploymentUsers`)

**Old:** Optional `importUsers` nested input on `adoptDeployment`.
**New:** Split into a second mutation, `adoptDeploymentUsers` (or similar). Reasons:
- Caller needs to supply Airflow admin credentials (master username + password) so Houston can call the Airflow API to enumerate users. That doesn't belong on the adoption mutation.
- Could be slow (depends on Airflow user count). Separate mutation = clean timing.
- Customer can choose to skip user import entirely without making the adoption call complicated.

**Impact:** Drop `importUsers` from `AdoptDeploymentInput`. File a separate ticket for `adoptDeploymentUsers` mutation (takes deployment ID + Airflow admin credentials).

### A.5 — URL handling — Option B/C/D effectively collapse; only Option A works

**Old (m2-task-1 § URL handling):** Four options (A/B/C/D) for how APC handles the customer's webserver URL.
**New (Vishnu, in detail):**
- Cross-domain cookies don't work because of how the auth proxy / OAuth flow reads cookies + SOP rules — confirmed limitation.
- Customer's existing ingress can be reused via the **auth sidecar** mechanism (or BYO Nginx ingress with extra annotations).
- For OpenShift: customer's ingress controller is reused; `*.openshift-base-domain.com` is whitelisted.
- After adoption, when the deployment is edited via Houston, all ingress objects auto-update to whatever pattern APC computes.

**Net effect:** Customer's existing URL is **not** preserved by APC. Houston rewrites the ingress on first edit (via SSA). What's preserved is the customer's *ingress controller / load-balancer IP* — APC reuses it instead of provisioning its own.

**Impact:** Simplify the URL-handling section. Drop the four-option table; replace with "APC's URL pattern wins on first edit; customer keeps their ingress controller via auth-sidecar / BYO-ingress." Also drop the `webserverUrl` field from `AdoptDeploymentInput` (Karan noted this in the meeting: *"based on the discussion, this field might not be required, so I'll update"*).

### A.6 — Disaster Recovery (DR) is **out of scope for v1**

**Old (m2-task-3 § E.4):** Metadata DB section mentioned `airflowDbRef.activeConnectionRef` / `inactiveConnectionRef`.
**New:** DR is a Helm-only feature in 0.37. Not supported for adopted operator deployments in v1. **No `inactiveConnectionRef` handling.**

**Impact:** Update Task 3 § E.4 — explicitly call out "DR not supported for adopted deployments in v1." The `airflowDbRef.activeConnectionRef` still gets populated (single connection); `inactive` stays null.

### A.7 — Logs / metrics — opt-in / opt-out, **no historical migration**

**Old (m2-task-3 § E.2, E.3):** Default switch to APC's ES at adopt time.
**New (Vishnu, in detail):**
- **Customer chooses at adopt time** — opt-in to APC's logging/metrics, or opt-out (keep their existing S3-based / Prometheus federation).
- If opt-out: APC's Vector / Elasticsearch / Prometheus components are **disabled from the helm chart** for that deployment (or globally — TBD). APC doesn't ship logs at all.
- If opt-in: **only post-adoption logs/metrics** are visible. APC does not migrate historical logs from customer's S3/ES.
- For federated Prometheus: customer can grant APC read access to their federated Prometheus; APC queries it directly. Requires `relabel_config` on the customer's side.

**Impact:** Update Task 3 § E.2 + E.3:
- Add an `optInToApcLogging: Boolean` / `optInToApcMetrics: Boolean` to `AdoptDeploymentInput`.
- Document the opt-out path: chart-side disablement of Vector / ES / Prometheus for that deployment.
- Document the federated Prometheus pattern as the recommended opt-in for customers who already have central observability.

### A.8 — Registry — explicit choice between BYO vs APC's in-cluster

**Old (m2-task-3 § E.5):** Keep customer's registry secret. Switch to APC's registry not in v1.
**New (Vishnu):** Make this an **explicit choice** at adopt time.
- **BYO (JFrog / Nexus / customer's private registry):** Customer provides registry URL + credentials. APC uses them directly. Standard case.
- **APC's in-cluster registry:** Customer must **re-synchronise all images** to APC's registry first (`registry.<baseDomain>/<workspaceId>/<releaseName>/airflow:<tag>`). Out-of-band operation. Then they can adopt with APC's registry as the source.

**Impact:** Update Task 3 § E.5 to surface the choice. Add a `useApcRegistry: Boolean` (default false) to `AdoptDeploymentInput`. Document the re-sync operation as a customer-driven prerequisite.

---

## B. New action items — content to add to design docs

### B.1 — Namespace pool handling (Vishnu)

Customer might be using **namespace pools** for their operator deployments. At DP provisioning time (Task 1), the generator script must:
- Detect existing namespaces hosting Airflow CRs.
- If pools are in use, pass the namespace list into the operator config (operator supports a `--namespaces` flag).

**Action:** Add to m2-task-1 § Survey logic. Add an open question on whether APC needs to track namespace pools in Houston too.

### B.2 — Auth sidecar / BYO ingress prerequisite

The auth-sidecar mechanism is a **hard prerequisite** when the customer's ingress controller is anything other than APC-provisioned NGINX. Document the two paths:
- Customer uses NGINX ingress already → just add auth-related annotations to their ingress, no sidecar needed.
- Customer uses OpenShift's default ingress / any other controller → enable APC's auth sidecar.

**Action:** Add to m2-task-1 § Survey logic. The survey should detect the customer's ingress controller type.

### B.3 — Operator-side reconciliation-pause flag

Vishnu mentioned: *"there is a specific flag you can enable that will pause that particular deployment to get updated from the operator."* This is the same pattern Astro uses for debugging.

**Action:** Karan to investigate which flag this is in the airflow-operator code (`AirflowReconciliationPausedUntilAnnotation` was mentioned earlier in our design — confirm). Document how the per-deployment freeze flag (A.1) interacts with this operator-side annotation — should APC set the annotation when `isFrozen=true`, so the operator also stops reconciling?

### B.4 — Async / wait-for-status (Vishnu's late comment)

Like the Helm flow, `adoptDeployment` returns as soon as Commander accepts the apply. It does **not** wait for the operator to finish reconciling. For DR-like waits or status polling, Houston may need a `waitForStatus` helper.

**Action:** Add to m2-task-3 § Phase C resolver as a documented limitation: the mutation returns when Houston-side state is persisted; downstream Kubernetes reconciliation is async and observable via the standard deployment-status query.

### B.5 — External secret managers — write semantics confirmed

**Old (m2-task-3 § E.1):** External-secret-managed env vars are read-only in v1.
**Updated:** Vishnu confirmed Helm uses a "push-secret CR" pattern — when env vars are updated, APC writes a PushSecret CR; external-secrets-operator syncs it back to the external store. The K8s Secret is the materialised mirror.

This may be portable to operator mode. **Karan to confirm in a follow-up — he flagged he didn't fully understand the helm-side push-secret flow in the meeting.**

**Action:** Update m2-task-3 § E.1 once confirmed. May change the v1 stance from "read-only" to "write via PushSecret CR, same as helm-mode."

### B.6 — Customer's env-var secret name is read from the CR

**Confirmed by Vishnu:** The CR's `env[]` carries a `secretKeyRef` — that's where we get the secret name. No reliance on `<releaseName>-env` convention. Houston dynamically reads whatever the CR points at.

**Action:** Already partially in m2-task-3 § E.1 (`envSecretNames` from catalogue map). Tighten the language to make it explicit: **no naming convention required; we read the reference directly.**

### B.7 — Airflow user creation on first SSO login

**Confirmed by Vishnu:** When a user with a valid Houston role binding (DEPLOYMENT_*, WORKSPACE_*, SYSTEM_*) clicks "Open Airflow" for the first time, the `AirflowAstroSecurityManager` auto-creates the `ab_user` row from the JWT claims. No pre-population needed.

**Implication:** Bulk user import (A.4 / `adoptDeploymentUsers`) is mostly redundant for SSO-backed customers. Only matters for FAB-DB customers who want their existing local Airflow users pre-mapped to APC.

**Action:** Add to m2-task-3 § D.2 (user import). Document that for SSO-backed Airflow, bulk import is largely a no-op.

### B.8 — F02 → F03 upgrade is **out of scope**

**Discussed:** BofA is currently blocked on F02 → F03; operator 1.5.x doesn't support the upgrade path.

**Confirmed:** Not in scope for this project. Sudarshan's project covers it. Karan has a follow-up with Ian.

**Action:** Add to the explicit out-of-scope list in m2-task-3 / overview.

---

## C. Scope confirmed (no change, but worth recording)

| Item | Status |
|---|---|
| Astro Runtime Operator only — not OSS / other operators | Confirmed prerequisite |
| F02 → F03 upgrade | Out of scope |
| DR (active / inactive connection refs) | Out of scope for v1 |
| DAG-only deploy / git-sync | Out of scope for v1 (only image-based DAG deploys) |
| LocalExecutor | Out of scope for v1 (CeleryExecutor + KubernetesExecutor only) |
| UI adopt wizard (Epic 8) | Stretch — CLI sufficient for v1 |
| Bulk discovery (`ListCustomResources` RPC) | Out of scope — operator uses `kubectl get airflows -A` |
| Two flow shapes in v1 | (1) Adoption of operator-mode deployments, (2) Default mechanism for creating new operator-mode deployments. |

---

## D. Open follow-ups (need owner / decision)

- [ ] **Product:** Confirm bulk user import (`adoptDeploymentUsers` mutation) is wanted for v1, or defer entirely. *(Karan/Nick — Nick is out; close before code freeze.)*
- [ ] **Karan:** Confirm with Ian (call tomorrow):
  - F02 → F03 upgrade path for the standalone operator (BofA blocker).
  - Whether the operator supports a per-CR reconciliation-pause flag and what its exact name is.
- [ ] **Karan:** Understand the helm-side push-secret CR flow before finalising m2-task-3 § E.1.
- [ ] **Karan:** Restructure the freeze flag: per-deployment, generic across modes (helm + operator + adopted). File a separate ticket — this is no longer just an operator-inheritance feature.
- [ ] **Karan:** Investigate auth-sidecar + BYO ingress detection in the survey step (Task 1).
- [ ] **Srini:** Test plan document.
- [ ] **Karan:** Update the design docs with everything above. Apply in order:
  1. Section A items (decision changes).
  2. Section B items (additions).
  3. Drop the items that became out-of-scope per Section C.
- [ ] **Karan:** Update the roadmap/tickets doc to reflect:
  - New ticket: `freezeDeployment` / `unfreezeDeployment` mutations + Prisma migration.
  - New ticket: `adoptDeploymentUsers` mutation (P2 — product-gated).
  - Drop ticket: `OPERATOR_INHERITANCE_FREEZE_EDITS` install-wide flag.
  - Drop ticket: `webserverUrl` handling work in Phase E.
  - Add ticket: opt-in/opt-out fields (`useApcLogging`, `useApcMetrics`, `useApcRegistry`) on `AdoptDeploymentInput`.

---

## E. Sprint / shipping cadence (decided)

- **Code freeze:** ~1 month before July 28 release (Rishab to confirm exact date).
- **Increments:** Bi-weekly drops to Kia (Srini's team) for testing — even if just the API surface. Don't bunch everything into the last sprint.
- **First milestone:** Task 3 / adoption end-to-end (mutation + per-deployment freeze + soft-delete + opt-in/opt-out for logs/metrics/registry). Task 1 (DP install) is parallel chart-team work.
- **Second milestone:** Default operator-mode provisioning (the forward flow, not just adoption). This is part of the broader scope confirmed in Section C.

---

## F. What I plan to do next (waiting on your approval)

Once you sign off on this summary:

1. Apply A.1–A.8 to `m2-task-1`, `m2-task-2`, `m2-task-3` (GitHub) and the Notion design doc.
2. Add B.1–B.8 as new sub-sections / open-questions in the relevant docs.
3. Update `tickets/adopt-deployment-mutation.md` to flip `acceptIncompatibilities` default to true + drop `webserverUrl` + drop `importUsers`.
4. Draft the new tickets (per-deployment freeze, `adoptDeploymentUsers`) in `tickets/`.
5. Update `roadmap-and-tickets.md` milestone & sprint allocations.

Tell me what to keep, edit, or drop from this list — and which items are blocked on the follow-ups in Section D.
