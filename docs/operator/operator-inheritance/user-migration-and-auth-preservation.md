# User migration & auth preservation for adopted deployments

Status: design captured from grooming (PLX-507 + a new auth-preservation guard). Not yet on Linear — recorded here intentionally.

Scope: how Houston handles **users and Airflow webserver auth** when APC adopts an operator-managed `Airflow` CR. Covers PLX-507 (`bulkUserImport`) and the decision to **preserve the customer's auth surface** rather than take it over in v1.

## TL;DR

1. **The Airflow CR carries no user roster.** `op.yaml` (Standard Chartered) and the Wellpartner CRs (`astro-airflow-platform.yaml`, `astro-airflow-dataops.yaml`) prove it: the only auth-relevant fields are `webserver.createDefaultUser` and `webserver.webserverConfig`. The users live in the **Airflow metadata DB** (FAB `ab_user`) or the customer's IdP — so import is **discover → review → import** (Model C): a discovery query reads the FAB users via Commander, an admin curates, then `bulkUserImport` provisions the curated subset.
2. **Airflow UI auth for the adoption cohort is self-contained** (the customer's own `webserver_config.py` — LDAP/AD/OAuth — or the Airflow image default), and **does not route through Houston**. Houston's `/v1/authorization` JWT is only consumed when the webserver runs `AUTH_TYPE = AUTH_REMOTE_USER` + `AirflowAstroSecurityManager`, which the operator never sets and APC does **not** impose on adopted deployments.
3. Therefore **`bulkUserImport` is scoped to Astronomer-platform / Houston-gated access** (deployments UI, deploy, logs, API/CLI), **not** Airflow access.
4. **Preserve the customer's auth surface** (webserver config + ingress auth wiring) on every adopted apply. This is already the default behavior via the PLX-578 empty allowlists; we add **regression guards** to lock it.
5. **"Take over auth" is deferred and incremental** — a clean, additive opt-in layer that reuses `bulkUserImport` unchanged. No rework, no migration debt.

## How auth works across the two systems

### airflow-operator (`controllers/airflow/webserver_controller.go`)

Pure pass-through, no opinions:

- `spec.webserver.webserverConfig` (raw `webserver_config.py` python string) → if non-empty, written to ConfigMap `{webserver}-config`, mounted at `/usr/local/airflow/webserver_config.py` (`webserver_controller.go:41,473`). If **empty, nothing is mounted** (`:182`) — Airflow uses its **image-baked default** (FAB `AUTH_DB` in AF2).
- **No default Astro auth.** Zero references to `AUTH_REMOTE_USER` / `AirflowAstroSecurityManager`.
- `spec.webserver.createDefaultUser: true` → a K8s Job runs `airflow users create -r Admin -u admin -p admin` (`internal/airflow/webserver.go:60`) — a hardcoded `admin:admin` FAB user in the metadata DB.
- **AF2 only.** `Webserver` is "Airflow < v3 only" (`apis/airflow/v1beta1/airflow_types.go:175`); AF3 uses `APIServer`. So `webserver_config.py` auth is an AF2-only concept on both sides.
- **No ingress auth.** Only passes through customer `ingress.annotations`.

### houston-api

- APC's own webserver config (`WEBSERVER_CONFIGMAP_FOR_OPERATOR`, `src/lib/constants/index.js:868`) is `AUTH_TYPE = AUTH_REMOTE_USER` + `SECURITY_MANAGER_CLASS = AirflowAstroSecurityManager`. Built into `<release>-webserver-config` by `addWebserverConfigMapToConfigMaps` (`operator/index.js:928`, AF2 only via the `:1521` gate).
- Houston's `/v1/authorization` (`src/routes/v1/authorization/handler.js`) is called by NGINX `auth_request`; it checks the user's RoleBinding, maps it to an Airflow role (`mapLocalRoleToAirflowRole:260` — `deployment.airflow.admin→Admin`, `.user→User`, `.get→Viewer`), and returns `Authorization: Bearer <JWT>`. AF2 vs AF3 differ (`airflowV2JWT` legacy `roles` claim vs `airflowV3JWT` granular permissions; key `runtimeAirflowVersion.startsWith("3")`).
- The NGINX `auth-url` / `auth-response-headers` annotations are built in `src/lib/deployments/config/index.js:2645`.

**Dependency:** the Houston JWT is only honored when the webserver is configured with `AUTH_REMOTE_USER` + `AirflowAstroSecurityManager`. With any other `AUTH_TYPE` (e.g. the customer's `AUTH_LDAP`), Airflow authenticates directly and ignores the JWT — Houston RBAC does **not** gate the Airflow UI.

### Real-world auth shapes among adopters

| Shape | Example | Airflow auth | Houston JWT used? |
|-------|---------|--------------|-------------------|
| Custom `webserverConfig` | Wellpartner (`AUTH_LDAP`/AD, `AUTH_ROLES_MAPPING`) | Native LDAP | No |
| Empty `webserverConfig` + `createDefaultUser` | SCB `op.yaml` | Airflow default `AUTH_DB` + `admin:admin` | No |
| Astro-managed | APC-created only | `AUTH_REMOTE_USER` + Astro mgr | Yes |

## Preserve the customer's auth surface (the guard)

For an adopted deployment, APC must change **none** of the three layers that determine who Airflow trusts:

| Layer | Where APC sets it | Adopted behavior |
|-------|-------------------|------------------|
| `webserver_config.py` | `<release>-webserver-config` ConfigMap | Dropped — `APC_MANAGED_ADOPTED_CONFIGMAP_SUFFIXES = []` (`operator/index.js:1304`) |
| Houston `auth-url`/`auth-response-headers` ingress annotations | `config/index.js:2645`, lands in webserver/ingress spec | Preserved by omission — not in `APC_MANAGED_ADOPTED_SPEC_PATHS` (only `statsd.customLabels`, `operator/index.js:1279`) |
| Standalone Ingress manifest | `k8sManifests` | Dropped — `k8sManifestsToApply = isAdopted ? [] : k8sManifests` (`operator/index.js:1741`) |

This is already true (PLX-578 seeded the allowlists empty). The **invariant to lock with tests**:

> APC must never, for an adopted deployment: (1) send `<release>-webserver-config`, (2) stamp the Houston `auth-url`/`auth-response-headers` annotations onto the webserver ingress, or (3) add an ingress route to the webserver Service that bypasses the customer's auth proxy.

This matters most for `AUTH_REMOTE_USER` customers: that auth type blindly trusts the upstream `REMOTE_USER` header, so any second network path or proxy swap introduced by adoption would be an auth bypass. Keeping all three layers customer-owned guarantees the `REMOTE_USER` source is unchanged.

## Model C: discover → review → import

The roster is **discovered from the adopted Airflow deployment's metadata DB**, reviewed by an admin, then imported. Three pieces:

### 1. Discovery — Commander `ListAirflowUsers` RPC (new)

The control plane **cannot reach the data-plane metadata DB directly** (it's in the DP; air-gapped for the target cohort). So discovery goes through Commander, which runs in the DP. New read-only RPC (mirrors the PLX-513 `ListCustomResources` style):

- `ListAirflowUsers(release_name, namespace, metadata_secret_name, correlation_id) → repeated AirflowUser{username, email, first_name, last_name, active, roles[]}`.
- Impl reads the metadata `Secret` (`connection` key = SQLAlchemy URI, `airflow-operator common.ConnectionKeyName`), normalizes the scheme to `postgres` (strips `+psycopg2`), connects via `lib/pq` (already a Commander dep), and `SELECT`s from the FAB `ab_user`/`ab_user_role`/`ab_role` tables.
- **AF2 + AF3-with-FAB:** the FAB tables are stable, so this works for both. **AF3 on a non-FAB auth manager** (SimpleAuthManager / AstroAuthManager / custom) has no `ab_user` → the impl detects `undefined_table` (SQLSTATE `42P01`) and returns a **failure `Result`** with a stable message (`"FAB user table (ab_user) not found; …"`), which Houston turns into a clear client error. This absent-table check is how we know the deployment isn't FAB-backed — no auth-manager introspection (exec / config API / CR parsing) needed.

**AF3 auth managers — handling non-FAB deployments.** AF3 replaced FAB with pluggable auth managers (`AIRFLOW__CORE__AUTH_MANAGER`); `airflow users create` is FAB-only and gone in AF3. Where users live depends on the manager: **SimpleAuthManager** (AF3 default) → config (`SIMPLE_AUTH_MANAGER_USERS`, auto-generated passwords; dev/testing) — no DB users; **FAB provider** (`apache-airflow-providers-fab`) → `ab_user` (queryable, AF2-parity); **AstroAuthManager** (`astronomer.runtime.auth_managers.astro.AstroAuthManager`, what APC-managed AF3 uses) → auth delegated to Houston, no Airflow-local users. Houston does **not** try to determine the auth manager itself (the effective value resolves across env > `airflow.cfg` > default and isn't reliably in the CR — verified live: `dynamical-cluster-8147`'s cfg says `SimpleAuthManager` but a pod env var overrides it to `AstroAuthManager`). Instead, **the absent `ab_user` table is the signal**: Commander's `ListAirflowUsers`, on Postgres `42P01` (undefined_table), returns a failure `Result` with a stable message (`"FAB user table (ab_user) not found; this deployment is not using a FAB auth manager"`); the `adoptedAirflowUsers` resolver inspects `response.result.success` and, when the message matches `ab_user`/`FAB auth manager`, throws a `UserInputError` telling the user the deployment uses a non-FAB auth manager (e.g. AF3 SimpleAuthManager / AstroAuthManager) — the UI surfaces it. (Rejected alternatives: reading `AIRFLOW__CORE__AUTH_MANAGER` from the CR — too narrow; a wrapper return type with a typed `reason` — a breaking schema change that broke a working AF2 deployment; Commander exec / the Airflow `/config` REST API — more infra for no gain over error-parsing.) The reference test-data CRs are all AF2/FAB.
- Files: `commander/_proto/airflow.proto` (messages) + `commander.proto` (RPC) · `commander/api/airflow_users.go` (handler) · `commander/provisioner/provisioner.go` (interface) · `commander/provisioner/kubernetes/airflow_users.go` (impl). **Requires `make build-proto`** to regenerate `pkg/proto`. (Houston's vendored `node_modules/commander/_proto` is also stale until the commander dep is bumped — the discovery query degrades to a `CommanderUnreachableError` until then, same caveat as PLX-578.)

### 2. Review — Houston `adoptedAirflowUsers(deploymentId)` query

Returns `[AdoptedAirflowUser]` — for FAB-backed deployments it calls the RPC and each entry = the FAB user + a **suggested Houston-role mapping** (non-FAB AF3 managers return an empty list). Astronomer's deployment model is 3 tiers that map 1:1 to the FAB roles Astronomer uses (`FAB_MANAGER_ROLES` = Admin/User/Viewer) — the canonical pairing Houston already uses in reverse (`mapLocalRoleToAirflowRole`, FAB `User` ↔ `DEPLOYMENT_EDITOR`): FAB `Admin`→`DEPLOYMENT_ADMIN`, `User`→`DEPLOYMENT_EDITOR`, `Viewer`→`DEPLOYMENT_VIEWER` (most-privileged-wins across a user's roles). Any other FAB role — stock `Op` (no Astronomer equivalent) or custom (`QA`/`Production Support`) → `suggestedDeploymentRole: null`, reviewer must choose. `suggestedWorkspaceRole` always `WORKSPACE_VIEWER`. Each candidate also carries **`alreadyImported`** — true when the email already belongs to a Houston user with a role binding in this deployment's workspace (matched case-insensitively; pending or active). The UI **hides already-imported users by default** (toggle to show) and disables their selection, since re-importing a workspace member would be rejected by `createRoleBindings` (duplicate workspace binding) — manage those on the Users tab. Read-only, grants nothing. apc-ui renders this for curation. Gated by the same `workspace.iam.update` (deployment-derived) check as the import.

### 3. Import — `bulkUserImport`

Provision Houston `User`s + workspace/deployment `RoleBinding`s for the **curated subset**, granting access to **Houston-gated surfaces** (deployments UI, deploy, logs, API/CLI). Not Airflow-UI access.

**Why `workspaceRole` is required (not optional):** Houston enforces that a deployment role cannot exist without workspace membership — `deploymentAddUserRole` hard-rejects ("does not belong to the workspace … cannot be assigned a deployment role"), the deployment `RoleBinding` row itself connects both `workspace` and `deployment`, and `createRoleBindings` always creates the workspace binding first. So each imported user gets workspace membership (`WORKSPACE_VIEWER` baseline, which cascades to deployment view) **plus** an optional `deploymentRole` elevation on the adopted deployment.

```graphql
bulkUserImport(
  deploymentId: Uuid!
  users: [UserImportInput!]!
  bypassInvite: Boolean = false
): [UserImportResult!]!

input UserImportInput {
  email: String!
  fullName: String
  workspaceRole: Role = WORKSPACE_VIEWER   # must start with WORKSPACE_
  deploymentRole: Role                      # optional; must start with DEPLOYMENT_
}

type UserImportResult {
  email: String!
  userId: String
  status: String        # active | pending
  created: Boolean!     # true if a new (pending) user was created
  rolesAssigned: [String!]!
  inviteToken: String   # present only when an invite token was generated and not bypassed
  error: String         # set instead of the above when that row failed
}
```

Behavior:

- Workspace derived from `deploymentId` (one mutation per adopted deployment).
- Per-row, reusing `createUser`/`createRoleBindings` (`src/lib/users/index.js`): existing active user → add bindings only (`created:false`); otherwise create a pending user + token + bindings (`created:true`). Idempotent; per-row errors captured in `error` (partial-failure reporting) rather than failing the whole batch.
- `bypassInvite` defaults **false** (corrected 2026-06-22). **Imported users get NO password — `bulkUserImport` creates a pending invite + role bindings, never a `LocalCredential`.** A password is only set when the *user* completes signup (`createUser` with their invite token), or they never need one under SSO (first SSO login links `OAuthCredential` by email and activates the pending user). So:
  - `bypassInvite: false` (default) → a `user-invite` token is generated; `sendEmail` delivers it if SMTP is configured (and safely **skips** when `email.enabled=false` — `emails/index.js:62,80`, never throws), and the per-row `inviteToken` is **returned** for out-of-band delivery on air-gapped installs. The user sets their own password at the signup page.
  - `bypassInvite: true` → no email, token is the `INVITE_BYPASS_TOKEN` sentinel (not delivered). Only suitable for **SSO-only** platforms where users never set a password. Setting this on a local-auth platform strands the user (no email, no usable token, no password) — this was the original wrong default.
- Permission gate: `workspace.iam.update` (same as `workspaceAddUser`).
- **SCIM**: if any active IdP has SCIM enabled (`isScimEnabled`), reject the whole mutation with `ScimEnabledUpsertEntityNotSupportedError` — users are owned by the IdP. (Open question: allow role-binding-only for already-provisioned users.)

### Out of scope
- Airflow-UI auth (preserved native `webserverConfig`).
- Migrating Airflow FAB/LDAP users from the metadata DB.
- SCIM-managed provisioning (owned by the IdP).
- "Take over auth" (below).

### Open questions
1. SCIM: hard reject vs role-binding-only for IdP-provisioned users.
2. AF2 vs AF3 — only AF2 has a `webserver_config.py`; AF3-on-SimpleAuthManager has no `ab_user` (discovery returns empty). Confirm the adoption-cohort runtime→Airflow-version mapping and how AF3 deployments are handled.
3. **Identity matching** — the FAB `username` is often `sAMAccountName` (LDAP), not the email/identity Houston logs in with. Discovery returns the `ab_user.email` column; confirm that's the right key to match/dedupe against Houston `User.username`/`Email` for the cohort's IdP.
4. For LDAP-backed deployments, `ab_user` is a **login cache** (only those who've logged in) — the full roster lives in AD. The discovered set may be incomplete; the review UI should make that clear (admin can add others manually via the import).
5. Is platform access even needed for customers who only use the Airflow UI?

## Deferred: "take over auth" (incremental, no rework)

A future opt-in where APC gates the adopted deployment's Airflow UI through Houston. It is purely additive on top of the preserve default, because the adopted apply is built around opt-in allowlists ("seeded empty — riders append their suffix(es)"):

1. add a per-deployment opt-in flag (add it *when building this*, not as a dead field now — cf. the `useApcRegistry` drop in PLX-506);
2. append `-webserver-config` to `APC_MANAGED_ADOPTED_CONFIGMAP_SUFFIXES` (impose `AUTH_REMOTE_USER` + Astro manager) and the ingress `auth-url` annotation path to `APC_MANAGED_ADOPTED_SPEC_PATHS`;
3. reuse `bulkUserImport` (the Houston→Airflow role mapping already exists) — only here does it gate Airflow access.

The allowlists are code constants, not DB, so flipping a deployment preserve→take-over later is a gated code change, not a migration. Keeping `bulkUserImport` modeled as generic Houston-RBAC provisioning (never "Airflow access semantics") is what keeps this free.

## Key files

- houston-api: `src/lib/deployments/operator/index.js` (`APC_MANAGED_ADOPTED_CONFIGMAP_SUFFIXES:1304`, `APC_MANAGED_ADOPTED_SPEC_PATHS:1279`, `scopeAdoptedApplyObjects:1328`, `scopeAdoptedApplySpec:1319`, `addWebserverConfigMapToConfigMaps:928`, apply `:1700+`) · `src/lib/constants/index.js:868` (`WEBSERVER_CONFIGMAP_FOR_OPERATOR`) · `src/lib/deployments/config/index.js:2645` (ingress auth annotations) · `src/routes/v1/authorization/handler.js` (Airflow JWT, `mapLocalRoleToAirflowRole:260`) · `src/lib/users/index.js` (`createUser:49`, `createRoleBindings:305`, `validateEmailAddress:235`) · `src/resolvers/mutation/workspace-add-user/index.js` (pattern) · `src/resolvers/query/idp-config/index.js` (`isScimEnabled`)
- houston-api (new, this work): `src/resolvers/mutation/bulk-user-import/index.js` (+ test) · `src/resolvers/query/adopted-airflow-users/index.js` (+ test) · `UserImportInput`/`UserImportResult`/`AdoptedAirflowUser` in `src/schema/types.js` · `bulkUserImport` in `src/schema/mutation.js` · `adoptedAirflowUsers` in `src/schema/query.js` · `hasDeploymentUserAdminPermission` + shields in `src/schema/permissions.js` · `src/lib/graphql/action-mapping.ts`
- commander (new, this work): `_proto/airflow.proto` + `_proto/commander.proto` (`ListAirflowUsers`) · `api/airflow_users.go` · `provisioner/provisioner.go` · `provisioner/kubernetes/airflow_users.go` (FAB DB read). Run `make build-proto` to regenerate `pkg/proto`.
- apc-ui (new, this work): `src/api/query/useAdoptedAirflowUsers.ts` (+ test) · `src/api/mutate/useBulkUserImport.ts` · `src/components/deployments/ImportUsers/DeploymentImportUsers.tsx` (full-page review table: include checkbox + per-row workspace/deployment role selects + bypassInvite [default OFF], calls `bulkUserImport`; already-imported users hidden by default with a "Show N already-imported" toggle + "Imported" badge + disabled selection; post-import results panel surfacing per-row signup tokens) · page wrapper `src/pages/workspace/deployments/DeploymentImportUsers.tsx` · route `import-users` in `src/App.tsx` · `deploymentImportUsers` in `src/utils/url.ts` · **"Import Users" tab** in `src/layouts/DeploymentDetailLayout.tsx` (sibling of Deploy History / Settings / Variables / Users, `isHidden` unless `deployment.isAdopted`). It is a **per-deployment tab**, NOT a Settings section. Requires bumping `.houston-api-types-version` + `yarn gen:types` after Houston publishes the new surface, so the generated `AdoptedAirflowUsers*`/`BulkUserImport*`/`UserImportInput` types exist. Tab visibility keys on `isAdopted` + `userManagementEnabled`; the server shield (`workspace.iam.update`) is the real authorization (a dedicated `canImportAirflowUsers` capability is a follow-up).
- airflow-operator: `controllers/airflow/webserver_controller.go` · `internal/airflow/webserver.go` · `apis/airflow/v1beta1/webserver_types.go:163` · metadata secret key `connection` (`controllers/airflow/common/common.go:77`)
- Sample CRs: `houston-api/test-data/op.yaml`, `astro-airflow-platform.yaml`, `astro-airflow-dataops.yaml`
