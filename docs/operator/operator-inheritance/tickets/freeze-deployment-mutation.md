# Ticket — `freezeDeployment` / `unfreezeDeployment` GraphQL mutations in Houston

> Generic per-deployment freeze. **Not** scoped to Operator Inheritance — works for helm, vanilla operator, and adopted operator deployments. Adoption is one consumer (per design-review A.1 in [`../design-review-action-items.md`](../design-review-action-items.md)); this ticket files the feature itself.

---

## Ticket metadata

| Field | Value |
|---|---|
| **Team** | PLX (Platform Experience) |
| **Project** | _none — standalone feature; Operator Inheritance is one consumer but doesn't own this_ |
| **Priority** | P0 (must ship — gates the Operator Inheritance rollback story) |
| **Estimate** | M (3–5 days) |
| **Depends on** | — |
| **Blocks** | Operator Inheritance § Phase F (rollback). Useful broadly for helm-mode debugging too. |
| **Labels** | `houston`, `graphql`, `deployment-lifecycle`, `rollback`, `v1` |

---

## Summary

Add a per-deployment **freeze** flag (`Deployment.isFrozen`) and two new mutations (`freezeDeployment`, `unfreezeDeployment`) that toggle it. When `isFrozen=true`, every Houston worker that calls Commander short-circuits before the call — no `ApplyCustomResource`, no `DeleteCustomResource`, no helm-mode `updateDeployment`. The deployment becomes operationally read-only from APC's side. The underlying Kubernetes resources keep running normally (helm release stays installed; airflow-operator keeps reconciling its CR; etc.).

**Why a separate mutation (not extending `upsertDeployment`)** — see § *Why separate mutations* below.

---

## Use cases

1. **Adoption rollback (the immediate trigger).** When an adopted CR's edits start misbehaving, freeze that one deployment while we fix forward. Don't break the customer's other deployments.
2. **Helm-mode debugging.** A deployment is stuck mid-rollout, support engineer wants to halt APC edits while they investigate without rolling back the whole Commander binary.
3. **Customer-requested freeze.** Customer asks "please stop pushing changes to this deployment for the next hour while we run a maintenance window." Operator flips the flag, customer does their thing, operator unfreezes.
4. **Field-engineering safety.** Before risky operations (large config migrations, executor changes), freeze the deployment so no concurrent edit can interfere.

---

## Why separate mutations (not extending `upsertDeployment`)

We considered piggybacking on `upsertDeployment` with a new `isFrozen: Boolean` arg. Rejected for five reasons:

| Concern | Separate mutation | Extending `upsertDeployment` |
|---|---|---|
| **Worker fan-out** | Resolver updates the row + audit log; no worker event published. | `upsertDeployment` always publishes `DEPLOYMENT_UPSERTED_*` events. The worker fires, sees `isFrozen=true`, no-ops. Wasted round-trip. |
| **Semantics** | Mutation name says what it does. | Freeze is operational state; `upsertDeployment` is for deployment config. Mixing them muddies the API. |
| **Permission scoping** | New permission `*.deployments.freeze` — support engineers can have freeze rights without full edit rights. | Shield rules are mutation-level; can't separate the perm from the rest of upsert. |
| **Audit clarity** | `action="freeze"` / `"unfreeze"` clearly labeled in the audit log. | `action="upsertDeployment", changedFields=["isFrozen"]` — harder to grep. |
| **In-flight edits** | Freeze takes effect at row-update; next worker call short-circuits. | Both share the same publish path; freeze event can race with the customer's edit event. |

Separate mutations win on every axis. The only thing extending `upsertDeployment` saves is "one less mutation in the schema" — not enough to justify the trade-offs.

---

## Request — GraphQL schema

Add to [`houston-api/src/schema/mutation.js`](../../../../../houston-api/src/schema/mutation.js):

```graphql
extend type Mutation {
  """
  Freeze a deployment — block all subsequent APC-driven edits to its underlying Kubernetes
  resources. Generic across modes: works for helm-mode, operator-mode, and adopted operator
  deployments. Houston workers check Deployment.isFrozen before any Commander call and
  short-circuit when true. The deployment's running pods are NOT touched; only future edits
  pushed from APC are blocked. Use unfreezeDeployment to lift.

  Idempotent: calling on an already-frozen deployment is a no-op (returns the deployment
  unchanged but does NOT write a second audit entry).
  """
  freezeDeployment(deploymentUuid: ID!, reason: String): Deployment!

  """
  Unfreeze a deployment — resume normal APC-driven edits. Idempotent.
  """
  unfreezeDeployment(deploymentUuid: ID!): Deployment!
}
```

### Example requests

```graphql
mutation FreezeDeployment {
  freezeDeployment(
    deploymentUuid: "ckxxxxxxxxxxxxxxxxxxxxxxxxx"
    reason: "KEDA scaler misbehaving; debugging — ticket SUPPORT-1234"
  ) {
    id
    label
    isFrozen
    frozenAt
    frozenReason
    frozenBy { id username }
  }
}

mutation UnfreezeDeployment {
  unfreezeDeployment(deploymentUuid: "ckxxxxxxxxxxxxxxxxxxxxxxxxx") {
    id
    label
    isFrozen
  }
}
```

---

## Schema additions

Prisma migration on the `Deployment` model:

```prisma
model Deployment {
  // ... existing fields ...
  isFrozen      Boolean   @default(false)
  frozenAt      DateTime?
  frozenReason  String?
  frozenById    String?
  frozenBy      User?     @relation("FrozenBy", fields: [frozenById], references: [id])
}
```

GraphQL `Deployment` type gains:
- `isFrozen: Boolean!`
- `frozenAt: DateTime`
- `frozenReason: String`
- `frozenBy: User`

---

## Permissions

Two new RBAC permissions registered in [`houston-api/src/lib/rbac/`](../../../../../houston-api/src/lib/rbac/):

| Permission | Granted to | Notes |
|---|---|---|
| `workspace.deployments.freeze` | `WORKSPACE_ADMIN` on the deployment's workspace | Workspace admins can freeze deployments in their own workspace. |
| `system.deployments.freeze` | `SYSTEM_ADMIN` | Astronomer field engineers / customer system admins. |

**Why a new permission, not piggybacking on `*.deployments.upsert`:** the operational scenarios this serves include support engineers who should be able to halt a runaway deployment without having broader edit rights. Separating the permission lets us grant freeze-only access cleanly.

**Shield rules** (to add to [`houston-api/src/schema/permissions.js`](../../../../../houston-api/src/schema/permissions.js) near the existing `upsertDeployment` rule):

```js
freezeDeployment: and(
  isAuth,
  or(
    hasRBAC("workspace.deployments.freeze"),
    hasRBAC("system.deployments.freeze")
  )
),
unfreezeDeployment: and(
  isAuth,
  or(
    hasRBAC("workspace.deployments.freeze"),
    hasRBAC("system.deployments.freeze")
  )
),
```

Same permission gates both directions — if you can freeze, you can unfreeze.

---

## Worker enforcement

Workers that touch Commander check `Deployment.isFrozen` before any RPC call. Affected workers:

| Worker | File | Behaviour when `isFrozen=true` |
|---|---|---|
| `deployment-upserted-for-create` | `houston-api/src/workers/deployment-upserted-for-create/index.js` | Skip `Commander.createDeployment` / `ApplyCustomResource`. Log INFO with `{ deploymentId, frozen: true, branch: "skipped" }`. |
| `deployment-upserted-for-update` | `houston-api/src/workers/deployment-upserted-for-update/index.js` | Same — skip Commander call. |
| `deployment-image-update` | `houston-api/src/workers/deployment-image-update/` | Same. |
| `deployment-variables-updated` | `houston-api/src/workers/deployment-variables-updated/` | Same. |
| `deployment-deleted` | `houston-api/src/workers/deployment-deleted/` | Skip Commander call. **Houston-side soft-delete still proceeds** — freeze gates K8s operations, not Houston state changes. |

**Read-side queries** are unaffected. `listDeployments`, `deployment(id)`, `deploymentLogs`, `deploymentStatus`, etc. all return normal data including the `isFrozen` flag.

---

## Resolver behaviour

### `freezeDeployment`

1. Validate caller has permission (shield handles this).
2. Look up `Deployment` by `deploymentUuid`. Return `DEPLOYMENT_NOT_FOUND` if missing.
3. If `isFrozen === true` already, return the existing row unchanged (no-op, no audit entry).
4. Update the row: `isFrozen = true`, `frozenAt = now()`, `frozenReason = input.reason ?? null`, `frozenById = ctx.user.id`.
5. Emit audit entry: `action="freeze"`, `userId = ctx.user.id`, `deploymentId`, `reason`.
6. Return the updated deployment (with `frozenBy` Prisma-included).

### `unfreezeDeployment`

1. Validate permission (shield).
2. Look up Deployment. `DEPLOYMENT_NOT_FOUND` if missing.
3. If `isFrozen === false`, return unchanged (no-op).
4. Update the row: `isFrozen = false`, clear `frozenAt`, `frozenReason`, `frozenById`.
5. Emit audit entry: `action="unfreeze"`, `userId`, `deploymentId`.
6. Return the updated deployment.

Neither resolver publishes any pub/sub event. State changes happen on the Houston side only.

---

## Error codes

| `extensions.code` | When raised | Extensions |
|---|---|---|
| `DEPLOYMENT_NOT_FOUND` | `deploymentUuid` doesn't match an existing row | `{ deploymentUuid }` |
| `PERMISSION_DENIED` | Shield rejected (no `*.deployments.freeze` perm) | — |

Idempotency means we don't need an "already frozen" / "not frozen" error — both are silent no-ops.

---

## Acceptance criteria

### Functional

- [ ] Prisma migration adds `isFrozen`, `frozenAt`, `frozenReason`, `frozenById` columns to `Deployment`.
- [ ] GraphQL `Deployment` type exposes `isFrozen`, `frozenAt`, `frozenReason`, `frozenBy`.
- [ ] `freezeDeployment` and `unfreezeDeployment` mutations are filed in `mutation.js` with the exact signatures above.
- [ ] Shield rules added; new RBAC permissions `workspace.deployments.freeze` and `system.deployments.freeze` registered.
- [ ] Calling `freezeDeployment` updates the row, writes one audit entry, returns the updated deployment.
- [ ] Calling `unfreezeDeployment` clears the freeze fields, writes one audit entry, returns the updated deployment.
- [ ] Idempotency: calling either mutation when the deployment is already in the target state is a clean no-op (returns the row unchanged, no audit entry).
- [ ] Each affected worker (5 listed above) checks `Deployment.isFrozen` before any Commander call and short-circuits when true.
- [ ] `deployment-deleted` worker's Houston-side soft-delete proceeds even when `isFrozen=true` — only the Commander call is gated.
- [ ] Listing / querying frozen deployments works normally — only writes are blocked.

### Non-functional

- [ ] Mutation execution under 200 ms in the happy path (single Prisma update + audit-log insert).
- [ ] All errors carry structured `extensions.code`.
- [ ] Logs follow `@astronomer/astro-log` patterns with `{ userId, deploymentId, action, correlationId }` fields.
- [ ] Audit entries are append-only — neither mutation modifies prior audit entries.

### Tests

- [ ] Unit tests for both resolvers:
  - Happy path freeze + unfreeze
  - Idempotent re-freeze / re-unfreeze
  - `DEPLOYMENT_NOT_FOUND`
  - `PERMISSION_DENIED` (no role binding)
- [ ] Worker tests confirming each of the 5 affected workers short-circuits when `isFrozen=true`.
- [ ] Worker test confirming `deployment-deleted` still soft-deletes Houston-side when `isFrozen=true`.
- [ ] Audit-log test confirming exactly one entry per state-change (not per call).
- [ ] Integration test (separate, can be in a follow-up ticket): freeze a real helm-mode deployment, attempt `upsertDeployment(workers.replicas: N+1)`, verify no Commander call fires + deployment pods unchanged.

---

## Out of scope (not in this ticket)

- **UI surfaces** — buttons in the deployment-detail page to freeze/unfreeze, banner showing frozen state. File as a separate UI ticket once this lands.
- **CLI surfaces** — `astro deployment freeze` / `astro deployment unfreeze` subcommands. Follow-up CLI ticket.
- **Bulk freeze** — `freezeDeployments([uuid, uuid, …])` mutation. Defer until customer feedback warrants.
- **Time-bounded freezes** — `freezeDeploymentUntil(uuid, timestamp)`. Defer; operator can unfreeze manually for now.
- **Operator-side annotation sync** — propagating `Deployment.isFrozen` into the airflow-operator's `AirflowReconciliationPausedUntilAnnotation` so the operator also stops reconciling. Useful but adds Commander-side work; file separately if pilot customer requests.

---

## Open questions

- [ ] **Audit-log shape.** Reuse the existing audit-log helpers — confirm the canonical `{action, userId, entityId, entityType, ...}` shape with whoever owns audit-log conventions in Houston.
- [ ] **UI banner copy.** Marketing / product input on what the frozen-deployment banner says. Out of scope for this ticket but worth tracking.
- [ ] **Should `freezeDeployment` automatically also fire the airflow-operator's pause annotation for operator-mode deployments?** Vishnu mentioned the operator has such an annotation. If yes, we'd need a Commander side trip during the freeze mutation. Current proposal: **no** — keep this ticket Houston-only and file the operator-annotation work as a follow-up.
