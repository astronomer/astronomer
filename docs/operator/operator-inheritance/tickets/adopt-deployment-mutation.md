# Ticket — `adoptDeployment` GraphQL mutation in Houston

> Linear-ready ticket draft. **Not** filed in Linear yet — review here first, push to Linear after approval.

---

## Ticket metadata

| Field | Value |
|---|---|
| **Team** | PLX (Platform Experience) |
| **Project** | [Operator Inheritance](https://linear.app/astronomer/project/operator-inheritance-6426e0c693ab) |
| **Milestone** | M2.C — Houston adoption mutations |
| **Parent issue (Epic)** | Epic 3 — Houston adoption mutations (see [`../roadmap-and-tickets.md`](../roadmap-and-tickets.md)) |
| **Priority** | P0 (must ship) |
| **Estimate** | L (1–2 weeks) |
| **Sprint** | 1 (scaffolding) + 2 (full resolver) |
| **Depends on** | Epic 1 / Ticket 1.4 (Commander `GetCustomResource` handler), Epic 2 / Tickets 2.1–2.7 (catalogue map), Ticket 3.1 (`OPERATOR_INHERITANCE_ENABLED` flag), Ticket 3.3 (mutation schema) |
| **Blocks** | Epic 4 (worker branching), Epic 6 (Phase E infra), Epic 7 (CLI) |
| **Labels** | `operator-inheritance`, `houston`, `graphql`, `m2`, `v1` |

---

## Summary

Implement the `adoptDeployment` GraphQL mutation in Houston. The mutation creates a Houston `Deployment` row for an existing `Airflow` CR running in a customer-managed cluster — without re-creating or stomping any Kubernetes resources. It fetches the live CR via the new Commander `GetCustomResource` RPC, catalogue-maps it into Houston's data model, runs a compatibility check, persists the deployment with adoption metadata, and grants the caller `DEPLOYMENT_ADMIN`. **No worker event is published** — the standard create-worker path would call `ApplyCustomResource` and stomp the customer's CR.

Full design context: [`m2-task-3-migrate-deployments-to-cp.md` § Phase C](../m2-task-3-migrate-deployments-to-cp.md#phase-c--adopt).

---

## Context links

- Design doc: [`m2-task-3` § Phase C](../m2-task-3-migrate-deployments-to-cp.md#phase-c--adopt) (resolver flow)
- Worked example: [`reference-cr-mapping-walkthrough.md`](../reference-cr-mapping-walkthrough.md) (real 0.37 CR walked through the mapping)
- Reference: [`reference-0.37-operator-mode.md`](../reference-0.37-operator-mode.md) (how operator-mode works in APC 0.37)
- Companion ticket: `unadoptDeployment` mutation (Ticket 3.6 in the roadmap — separate ticket)
- Companion ticket: `GetCustomResource` RPC on Commander (Ticket 1.4)

---

## Permissions

The mutation uses Houston's existing `graphql-shield` + `hasRBAC()` pattern ([`houston-api/src/schema/permissions.js`](../../../../../houston-api/src/schema/permissions.js)). Two new permissions need to land alongside the existing `upsertDeployment` permissions:

| Permission | Granted to | Notes |
|---|---|---|
| `workspace.deployments.adopt` | `WORKSPACE_ADMIN` on the target workspace | Workspace-scoped — admins of the workspace can adopt CRs into their workspace. |
| `system.deployments.adopt` | `SYSTEM_ADMIN` | System-wide — Astronomer field engineers / customer system admins. |

**Why a new permission, not just `*.deployments.upsert`?** Adoption has different semantics from upsert: it touches existing K8s resources (read-side), creates Houston state that can't be trivially recreated, and produces audit trails distinct from regular deployment creation. A separate permission lets operators grant adoption rights without granting general deployment-edit rights, and vice versa.

**Shield rule** (to add to [`src/schema/permissions.js`](../../../../../houston-api/src/schema/permissions.js) ~line 580 next to `upsertDeployment`):

```js
adoptDeployment: and(
  isAuth,
  or(
    hasRBAC("workspace.deployments.adopt"),
    hasRBAC("system.deployments.adopt")
  )
),
```

**Additional gate (inside resolver, not shield):**

1. **Feature flag.** Reject with `OPERATOR_INHERITANCE_DISABLED` error if `config.get("operatorInheritance.enabled") !== true`. (See Ticket 3.1.)
2. **Workspace membership.** The caller must have a role binding on `workspaceUuid` (RBAC handles this implicitly via the `workspace.*` scope; defence-in-depth check in the resolver doesn't hurt).
3. **Cluster authorization.** The caller must have read access to `clusterId`. Reuse existing helpers — `hasSystemPermission(user, "system.cluster.get")` OR the user has any role binding referencing this cluster.

---

## Request — GraphQL schema

Schema additions to [`houston-api/src/schema/mutation.js`](../../../../../houston-api/src/schema/mutation.js) (next to `upsertDeployment` ~line 800):

```graphql
extend type Mutation {
  """
  Adopt an existing Airflow CR running in a DP cluster into Houston as a managed Deployment.
  Houston fetches the live CR from the cluster via Commander.GetCustomResource and catalogue-maps it.
  Does not modify any Kubernetes resources except for SSA patches that add labels APC's observability requires.

  Errors:
    - OPERATOR_INHERITANCE_DISABLED      feature flag is off
    - WORKSPACE_NOT_FOUND                workspaceUuid does not exist
    - CLUSTER_NOT_FOUND                  clusterId does not exist or caller has no access
    - CR_NOT_FOUND                       Airflow CR not present in (crNamespace, crName) on the cluster
    - DEPLOYMENT_ALREADY_EXISTS          Houston already has a deployment with this releaseName/namespace
    - ADOPTION_INCOMPATIBLE              Only when caller passed acceptIncompatibilities:false; CR has unmapped fields. Default true mode adopts anyway.
    - PERMISSION_DENIED                  caller lacks required RBAC
  """
  adoptDeployment(
    """APC workspace to attach the deployment to. Required."""
    workspaceUuid: Uuid!

    """Houston Cluster ID (from registerCluster) where the CR lives. Required."""
    clusterId: Uuid!

    """Kubernetes namespace of the Airflow CR. Required."""
    crNamespace: String!

    """metadata.name of the Airflow CR. Required."""
    crName: String!

    """UI display label. Defaults to crName when omitted."""
    label: String

    """Longer-form description. Maps to Deployment.description."""
    description: String

    """
    Default false. When true, APC's Elasticsearch/Vector becomes the deployment's log
    destination — Houston generates an ES user/password and SSA-patches the CR's ES env vars.
    When false (default), APC's logging stack is opted out for this deployment.
    Historical log migration is NOT supported either way.
    """
    useApcLogging: Boolean

    """
    Default false. When true, APC's Prometheus scrape config is wired up at adopt time.
    When false, customer keeps their existing Prometheus / federation setup.
    """
    useApcMetrics: Boolean

    """
    Default false. When false, APC uses the customer's existing registry (the CR's
    spec.image + imagePullSecret are recorded but not modified). When true, the customer
    must re-synchronise images to APC's in-cluster registry BEFORE running this mutation —
    failing that, pods can't pull images.
    """
    useApcRegistry: Boolean

    """
    Defaults to TRUE (per design-review A.2). When TRUE, the resolver always adopts the CR
    and stashes any unmapped fields in Deployment.config.adoption.rawCRSnapshot.
    When set explicitly to FALSE, the resolver returns a structured ADOPTION_INCOMPATIBLE
    error if any field has no Houston representation — strict mode for callers who want
    to fail loudly.
    """
    acceptIncompatibilities: Boolean
  ): Deployment!
}
```

> Arguments are **flat top-level fields** (no `input` wrapper).

> **Removed from the earlier draft per design review:**
> - `webserverUrl` (A.5) — APC's URL pattern wins on first edit. The customer's existing URL is *not* preserved; what's preserved is their ingress controller / LB IP.
> - `importUsers` block (A.4) — bulk Airflow user import is a separate, follow-up mutation `adoptDeploymentUsers` since it needs Airflow API admin credentials.

### Example request

```graphql
mutation AdoptDeployment(
  $workspaceUuid: Uuid!
  $clusterId: Uuid!
  $crNamespace: String!
  $crName: String!
  $label: String
  $description: String
  $useApcLogging: Boolean
  $useApcMetrics: Boolean
  $useApcRegistry: Boolean
  $acceptIncompatibilities: Boolean
) {
  adoptDeployment(
    workspaceUuid: $workspaceUuid
    clusterId: $clusterId
    crNamespace: $crNamespace
    crName: $crName
    label: $label
    description: $description
    useApcLogging: $useApcLogging
    useApcMetrics: $useApcMetrics
    useApcRegistry: $useApcRegistry
    acceptIncompatibilities: $acceptIncompatibilities
  ) {
    id
    releaseName
    namespace
    label
    mode
    config
    workspace { id label }
    cluster   { id name baseDomain }
    createdAt
  }
}
```

Variables:

```json
{
  "workspaceUuid": "cmpcqawyq020917jt789yw7fd",
  "clusterId":     "clw1abc234def567ghi890jkl",
  "crNamespace":   "airflow-prod",
  "crName":        "prod-airflow",
  "label":         "Production ETL",
  "description":   "Customer's production Airflow",
  "useApcLogging":  false,
  "useApcMetrics":  true,
  "useApcRegistry": false,
  "acceptIncompatibilities": true
}
```

---

## Response — success and error shapes

### Success

Returns the freshly-created `Deployment` row. Shape per the existing `Deployment` GraphQL type — the resolver does not need to add new fields. The key bits a UI / CLI consumer will care about:

```jsonc
{
  "data": {
    "adoptDeployment": {
      "id": "ckxxxxxxxxxxxxxxxxxxxxxxxxx",
      "releaseName": "prod-airflow",
      "namespace": "airflow-prod",
      "label": "Production ETL",
      "mode": "operator",
      "config": {
        "adoption": {
          "adopted": true,
          "adoptedAt": "2026-05-25T12:34:56Z",
          "source": "operator-cr",
          "platformRelease": "astronomer",
          "envSecretNames": ["prod-airflow-env"],
          "urls": { "webserver": "https://airflow.acme.com" },
          "registry": {
            "image": "quay.io/acme/airflow:1.0.0",
            "imagePullSecret": "prod-airflow-registry"
          },
          "specQuirks": {
            "airflow3xUsingWebserver": false,
            "dagProcessorPresentButDisabled": true
          },
          "rawCRSnapshot": { /* full .spec verbatim when partial/incompatible fields exist */ }
        }
      },
      "workspace": { "id": "cmpcqawyq020917jt789yw7fd", "label": "ACME Prod" },
      "cluster":   { "id": "clw1abc234def567ghi890jkl", "name": "acme-eu-dp", "baseDomain": "astro.acme.com" },
      "createdAt": "2026-05-25T12:34:56Z"
    }
  }
}
```

### Error — `ADOPTION_INCOMPATIBLE`

Returned **only when the caller explicitly passes `acceptIncompatibilities: false`** and the catalogue-map flags one or more unmapped CR fields. With the default (`true`), the resolver adopts the CR and stashes unmapped fields in `Deployment.config.adoption.rawCRSnapshot` instead.

```jsonc
{
  "errors": [{
    "message": "Cannot adopt deployment — CR has fields with no Houston representation.",
    "path": ["adoptDeployment"],
    "extensions": {
      "code": "ADOPTION_INCOMPATIBLE",
      "incompatibleFields": [
        { "path": "spec.airflowPlugins",         "reason": "no first-class Houston column" },
        { "path": "spec.podTemplateConfigMapName", "reason": "no first-class Houston column" }
      ],
      "partialFields": [
        { "path": "spec.workers", "reason": "multiple worker groups; first becomes default, others go to config.adoption.workerGroupsOverflow" }
      ]
    }
  }]
}
```

### Other errors

| `extensions.code` | When raised | Extensions |
|---|---|---|
| `OPERATOR_INHERITANCE_DISABLED` | Feature flag off | — |
| `WORKSPACE_NOT_FOUND` | `workspaceUuid` does not match a row | `{ workspaceUuid }` |
| `CLUSTER_NOT_FOUND` | `clusterId` does not match or caller has no access | `{ clusterId }` |
| `CR_NOT_FOUND` | `Commander.GetCustomResource` returned NotFound | `{ crNamespace, crName, clusterId }` |
| `DEPLOYMENT_ALREADY_EXISTS` | A non-soft-deleted Deployment row already has the same `releaseName` or `namespace` | `{ existingDeploymentId, conflictField }` |
| `IMAGE_NOT_REACHABLE_IN_APC_REGISTRY` | `useApcRegistry=true` but the image at `registry.<baseDomain>/<workspaceId>/<releaseName>/airflow:<tag>` isn't reachable. Customer needs to re-sync first. | `{ expectedImage, clusterId }` |
| `PERMISSION_DENIED` | Shield rejected (no `*.deployments.adopt` perm) | — (handled by `graphql-shield` default) |
| `COMMANDER_UNREACHABLE` | gRPC call to Commander failed (transport-level) | `{ clusterId, cause }` |
| `CATALOGUE_MAP_FAILED` | Unexpected error inside the catalogue-map module | `{ cause }` |

---

## Resolver flow (file: `houston-api/src/resolvers/mutation/adopt-deployment/index.ts`)

Matches the 11-step flow in [`m2-task-3` § Phase C](../m2-task-3-migrate-deployments-to-cp.md#phase-c--adopt). Brief recap:

1. **Feature flag.** Reject with `OPERATOR_INHERITANCE_DISABLED` if `config.get("operatorInheritance.enabled") !== true`.
2. **AuthZ defence-in-depth.** Verify caller has at least one role binding on `workspaceUuid` and read access to `clusterId`.
3. **Lookup workspace + cluster.** Reject with `WORKSPACE_NOT_FOUND` / `CLUSTER_NOT_FOUND` accordingly.
4. **(If `useApcRegistry=true`)** Verify the image at `registry.<helm.baseDomain>/<workspaceId>/<releaseName>/airflow:<tag>` is reachable from the DP. Reject with `IMAGE_NOT_REACHABLE_IN_APC_REGISTRY` if not — point the operator at the re-sync runbook.
5. **Fetch the live CR.** Call `Commander.GetCustomResource(group="airflow.apache.org", version="v1beta1", plural="airflows", namespace=crNamespace, name=crName)` against the cluster. Reject with `CR_NOT_FOUND` if missing.
6. **Catalogue-map.** Run `crToDeployment(crSpec, namespaceLabels, secrets)` from `lib/deployments/operator/cr-to-deployment.ts`.
7. **Compatibility gate.** `acceptIncompatibilities` defaults to `true` — adopt anyway and stash unmapped fields. Only when the caller explicitly passes `acceptIncompatibilities: false` AND `compatibility.incompatible.length > 0` do we throw `ADOPTION_INCOMPATIBLE`.
8. **Dedup check.** Search for any non-soft-deleted Deployment with `releaseName=crName` OR `namespace=crNamespace`. If found, return `DEPLOYMENT_ALREADY_EXISTS`. Special case: if the existing row is *soft-deleted* (a previously un-adopted deployment), restore it instead (clear `deletedAt`, refresh `config.adoption.rawCRSnapshot`) — covered in a separate ticket; for v1 of this ticket, just check non-soft-deleted.
9. **Set adoption metadata** in the upsert payload's `config.adoption.*`:
   - `adopted: true`
   - `adoptedAt: now()`
   - `source: "operator-cr"`
   - `platformRelease: <from namespace label, if present>`
   - `optIn: { logging: <input.useApcLogging>, metrics: <input.useApcMetrics>, registry: <input.useApcRegistry> }` — opt-in flags persisted for workers to read on subsequent edits.
   - `envSecretNames: <from catalogue map>`
   - `registry: { image, imagePullSecret }`
   - `specQuirks: { ... }`
   - `rawCRSnapshot: <full CR spec>` — **always populated** (because `acceptIncompatibilities` defaults to `true` and we never want to silently lose customer fields).
   - `incompatibleFields: <list>` — always populated when any exist; used for audit + future migration to first-class columns.
10. **Persist.** `prisma.deployment.create({ data: ..., include: { workspace, cluster, roleBindings: {...} } })`. **Do not** publish `DEPLOYMENT_UPSERTED_FOR_CREATE` or any other worker event.
11. **Create role binding.** `prisma.roleBinding.create({ data: { role: DEPLOYMENT_ADMIN, deploymentId, userId: ctx.user.id } })`.
12. **Audit log.** Reuse existing audit-log helpers — entry: `{ action: "adopt", userId, deploymentId, releaseName, namespace, clusterId, workspaceUuid, incompatibilitiesAccepted }`.
13. **Return** the Deployment record (with workspace + cluster + roleBindings via Prisma `include`).

---

## Acceptance criteria

### Functional

- [ ] Mutation is filed in [`houston-api/src/schema/mutation.js`](../../../../../houston-api/src/schema/mutation.js) with the exact input type signature above.
- [ ] Shield rule added to [`src/schema/permissions.js`](../../../../../houston-api/src/schema/permissions.js).
- [ ] Two new permissions registered: `workspace.deployments.adopt` (granted to `WORKSPACE_ADMIN`) and `system.deployments.adopt` (granted to `SYSTEM_ADMIN`).
- [ ] Resolver lives at `houston-api/src/resolvers/mutation/adopt-deployment/index.ts` and implements steps 1–13.
- [ ] Calling the mutation when `OPERATOR_INHERITANCE_ENABLED=false` returns `OPERATOR_INHERITANCE_DISABLED`.
- [ ] Calling the mutation as a user without `*.deployments.adopt` returns `PERMISSION_DENIED` (handled by shield).
- [ ] Calling the mutation with a non-existent `workspaceUuid` returns `WORKSPACE_NOT_FOUND`.
- [ ] Calling the mutation with a non-existent `clusterId` returns `CLUSTER_NOT_FOUND`.
- [ ] Calling the mutation when the target CR doesn't exist returns `CR_NOT_FOUND`.
- [ ] Calling the mutation with `useApcRegistry=true` when the expected image isn't pre-synced to APC's registry returns `IMAGE_NOT_REACHABLE_IN_APC_REGISTRY`.
- [ ] Calling the mutation when a Deployment with the same `releaseName` or `namespace` exists returns `DEPLOYMENT_ALREADY_EXISTS`.
- [ ] Successful mutation creates a `Deployment` row with `mode="operator"`, `config.adoption.adopted=true`, `isFrozen=false`, and the expected `config.adoption.*` sub-fields populated (including `optIn.{logging,metrics,registry}` reflecting the input).
- [ ] Successful mutation creates exactly one `RoleBinding` (role=`DEPLOYMENT_ADMIN`, userId=caller) tied to the new deployment.
- [ ] Successful mutation **does not** publish any pub/sub event. Verified by intercepting the publisher in test.
- [ ] Successful mutation writes one Houston audit-log entry with `action="adopt"`.
- [ ] **Default mode (`acceptIncompatibilities` omitted or true):** adoption succeeds even when CR has unmapped fields; `config.adoption.rawCRSnapshot` populated and `config.adoption.incompatibleFields` lists them.
- [ ] **Strict mode (`acceptIncompatibilities: false`):** when CR has unmapped fields, mutation returns `ADOPTION_INCOMPATIBLE` with `extensions.incompatibleFields` populated.

### Non-functional

- [ ] Resolver execution under 2 seconds in the happy path (one `Commander.GetCustomResource` round-trip + Prisma create + role-binding create).
- [ ] All errors carry a structured `extensions.code` per the Error Codes table above. No bare string errors.
- [ ] Logs follow the `@astronomer/astro-log` patterns — INFO on resolver entry/exit, WARN on validation failures, ERROR on Prisma/Commander failures. Each log line carries `{ userId, workspaceUuid, clusterId, crNamespace, crName, correlationId }`.
- [ ] No new dependencies added to `houston-api/package.json` (use existing gRPC client + Prisma + audit-log helpers).

### Tests

- [ ] **Unit tests** for the resolver covering each branch:
  - Feature flag off
  - Permission denied (rejected by shield)
  - Workspace not found
  - Cluster not found
  - Webserver URL off-domain
  - Commander returns NotFound for the CR
  - Catalogue-map produces incompatible fields → default mode (`acceptIncompatibilities` omitted) → adopt succeeds + `rawCRSnapshot` populated
  - Catalogue-map produces incompatible fields → `acceptIncompatibilities: false` (strict) → `ADOPTION_INCOMPATIBLE` error
  - `useApcRegistry: true` with image present in APC registry → success
  - `useApcRegistry: true` with image missing → `IMAGE_NOT_REACHABLE_IN_APC_REGISTRY`
  - Dedup check fires on existing same-releaseName deployment
  - Happy path
- [ ] **Pub/sub spy test** — assert zero `DEPLOYMENT_UPSERTED_*` events published during happy path.
- [ ] **Audit-log test** — assert one `adopt` audit entry written.
- [ ] **Integration test** (in a separate ticket, but listed here for traceability):
  - Pre-create an `Airflow` CR on k3d via `kubectl apply`.
  - Call the mutation via real Houston GraphQL endpoint.
  - Assert deployment row created.
  - Assert CR is unchanged in K8s (verify with `kubectl get`).

---

## Out of scope (handled by other tickets)

- **`unadoptDeployment` mutation** — separate ticket (Ticket 3.6 in roadmap).
- **Per-deployment freeze (`Deployment.isFrozen` + `freezeDeployment` / `unfreezeDeployment` mutations) and worker enforcement** — separate generic ticket outside operator-inheritance scope (A.1). Adoption flips `isFrozen=false` initially; the freeze ticket owns the flag plumbing.
- **Worker-side SSA path for adopted deployments** — Epic 4.
- **Per-deployment infrastructure handling (env vars writeback, metadata DB plumbing, registry recording)** — Epic 6. This ticket *records* the adoption metadata into `config.adoption.*`; downstream tickets consume it.
- **`GetCustomResource` RPC on Commander** — Ticket 1.4.
- **Catalogue-map module** (`cr-to-deployment.ts`) — Epic 2.
- **CLI `astro deployment adopt`** — Ticket 7.1.
- **UI adopt wizard** — Epic 8 (deferred).
- **Bulk Airflow user import (D.2)** — separate ticket, product-gated.

---

## Open questions

- [ ] **Workspace-scoped vs cluster-scoped permission.** Is `workspace.deployments.adopt` the right scope, or should adoption require `cluster.deployments.adopt` (since it's a per-cluster operation)? Current proposal: workspace-scoped, since the workspace is the unit of multi-tenancy in Houston. Alternative: add both and require either.
- [ ] **Soft-deleted dedup.** If a Deployment row with the same `releaseName` + `namespace` + `clusterId` exists but is soft-deleted (the customer previously un-adopted it), should this mutation restore it instead of returning `DEPLOYMENT_ALREADY_EXISTS`? Current proposal: out of scope for this ticket — file a follow-up to add re-adoption semantics.
- [ ] **Return shape.** Do we need to return the catalogue-map compatibility report alongside the deployment (`{ deployment, compatibility }`) so the UI can show "this deployment was adopted with these caveats"? Or keep it on `config.adoption.incompatibleFields` and let consumers read it from there? Current proposal: store on `config.adoption`, no separate return field.
- [ ] **Caller's role binding propagation.** Should the caller also get added as `WORKSPACE_EDITOR` if they don't already have a workspace role binding? Or rely on existing workspace membership? Current proposal: rely on existing membership (RBAC already gates the mutation).

---

## Notes for the implementer

- The `Deployment.config` column is `Json @db.JsonB` ([`prisma/schema.prisma`](../../../../../houston-api/prisma/schema.prisma)) — append-only JSON updates are safe via Prisma's `set` semantics.
- Use the existing audit-log helpers in `houston-api/src/lib/auditLog/` (or wherever your team standardised them) — do not roll a new audit pattern.
- Test against the worked-example CR in [`reference-cr-mapping-walkthrough.md`](../reference-cr-mapping-walkthrough.md) — that one was inspected on a live cluster and is the closest thing to a customer-realistic fixture.
- The mutation must **never** call `commander.request("ApplyCustomResource", ...)`. If you find yourself wanting to, you're on the wrong path — that's Epic 4's territory.
- `correlationId` should propagate from the gRPC context to Commander's call. Reuse Houston's existing correlation-id middleware.
