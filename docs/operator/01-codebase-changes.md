# Airflow Operator in APC 2.0 — Codebase Changes by Repository

**Linear Project:** [Install APC using an Operator](https://linear.app/astronomer/project/install-apc-using-an-operator-96722e2d8488)
**Design Doc:** [Airflow Operator in Software (Notion)](https://www.notion.so/astronomerio/Airflow-Operator-in-Software-eb22db0954f04eb5bb2b67d4540e5cc0)
**Original Epic:** [astronomer/issues#6740](https://github.com/astronomer/issues/issues/6740) (closed for 0.37)
**Linear Issues:** PLX-262 (Helm chart), PLX-263 (Houston), PLX-264 (Validation)

---

## Overview

The Airflow Operator was shipped as experimental in APC 0.37. The operator code paths already exist in the 2.0 codebase, carried forward from 0.37. This document tracks what exists, what needs updating, and what's missing per repository.

**Flow:** Astro UI -> Houston API -> (Pub/Sub) -> Houston Worker -> Commander (gRPC) -> K8s API -> Airflow Operator -> Airflow instance

---

## 1. Astronomer Helm Chart (`astronomer` repo)

### What Exists

| Component | Location | Status |
|-----------|----------|--------|
| Master switch | `values.yaml` -> `global.airflowOperator.enabled: false` | Present |
| Operator subchart | `charts/airflow-operator/` (14 CRDs, webhooks, manager deployment) | Present |
| Commander RBAC | `charts/astronomer/templates/commander/commander-role.yaml:44-48` | Present, conditional on flag |
| Prometheus scrape | `charts/prometheus/templates/prometheus-config-configmap.yaml:291-316` | Present, conditional on flag + clusterRoles |
| Houston config pass-through | `charts/astronomer/templates/houston/houston-configmap.yaml:99-101` | Present, minimal |
| Chart tests | `tests/chart_tests/test_airflow_operator.py` | Present |

### Key Files

```
astronomer/
  values.yaml                          # global.airflowOperator.enabled
  Chart.yaml                           # dependency: airflow-operator (condition: global.airflowOperator.enabled)
  charts/airflow-operator/
    Chart.yaml                         # version 0.1.0, appVersion 0.1.0
    values.yaml                        # image: 1.5.2, crd.create: false, certManager.enabled: false
    templates/
      crds/                            # 14 CRD definitions (airflow, scheduler, worker, etc.)
      manager/                         # controller-manager-deployment.yaml
      webhooks/                        # mutating + validating webhook configs
      rbac/                            # operator clusterrole, rolebinding
  charts/astronomer/templates/
    commander/commander-role.yaml      # airflow.apache.org RBAC (line 44-48)
    houston/houston-configmap.yaml     # deployments.mode.operator.enabled (line 99-101)
  charts/prometheus/templates/
    prometheus-config-configmap.yaml   # airflow-operator scrape job (line 291-316)
  tests/chart_tests/
    test_airflow_operator.py           # CRD, cert-manager, webhook tests
```

### What Needs To Be Done

- [ ] **Update operator image tag**: Chart has `1.5.2`, operator repo has `1.6.0-rc1`. Determine which version to ship with APC 2.0. Coordinate with operator team on a stable release.
- [ ] **Verify CRD sync**: Ensure the 14 CRDs in `charts/airflow-operator/templates/crds/` match the operator repo's `config/crd/bases/`. Look for any new fields added since 0.37.
- [ ] **Add MySQL probe config to Houston configmap**: Currently `houston-configmap.yaml` only passes `deployments.mode.operator.enabled`. Houston's operator code references `config.get("deployments.mode.operator.{component}.mysql.{probe}")` which will be undefined. Need to add MySQL probe defaults under the `mode.operator` section.
- [ ] **Verify PLX-254 compatibility**: The feature flag restructuring changed patterns like `global.openshiftEnabled` -> `global.openshift.enabled`. Confirm the operator subchart templates use the new patterns. Files to check:
  - `charts/airflow-operator/templates/_helpers.yaml`
  - `charts/airflow-operator/templates/manager/controller-manager-deployment.yaml`
- [ ] **Verify cert-manager dependency**: Operator webhooks require cert-manager. `certManager.enabled` defaults to `false` in operator values. When `global.airflowOperator.enabled` is set, cert-manager must be enabled. Consider adding a validation check.
- [ ] **Network policy review**: Verify that default-deny network policies don't block operator controller -> airflow pod communication. Check `templates/default-deny-network-policy/`.
- [ ] **Expand chart tests**: Add tests for:
  - Houston configmap operator config values
  - Commander RBAC includes airflow.apache.org when flag is on
  - Prometheus scrape job present when flag is on
  - cert-manager validation when operator enabled

---

## 2. Houston API (`houston-api` repo)

### What Exists

| Component | Location | Status |
|-----------|----------|--------|
| CRD spec generation | `src/lib/deployments/operator/index.js` (1498 lines) | Present, may need updates |
| DEPLOYMENT_MODE constant | `src/lib/constants/index.js:769-772` | Present (`helm`, `operator`) |
| Database mode field | `prisma/schema.prisma` -> `Deployment.mode` | Present |
| Create worker routing | `src/workers/deployment-upserted-for-create/index.js:274-311` | Present |
| Update worker routing | `src/workers/deployment-upserted-for-update/index.js:222+` | Present |
| Delete worker routing | `src/workers/deployment-deleted/index.js:218+` | Present |
| GraphQL mutation | `src/schema/mutation.js:800` -> `upsertDeployment(mode:)` | Present |
| Mode setter | `src/resolvers/mutation/upsert-deployment/index.ts:65` -> `setDeploymentMode()` | Present |
| Operator CRD constants | `src/lib/constants/index.js` -> `apiVersion: airflow.apache.org/v1beta1` | Present |

### Key Files

```
houston-api/
  src/lib/deployments/operator/
    index.js                           # Main CRD spec generation (1498 lines)
                                       # - getCRDSpecFromHelmValues()
                                       # - createOrUpdateDeploymentForOperatorMode()
                                       # - deleteDeploymentForOperatorMode()
                                       # - getSecretsForOperatorMode()
                                       # - getConfigMapsForOperatorMode()
                                       # - addSchedulerComponentToSpec()
                                       # - addWorkersComponentToSpec()
                                       # - addTriggererComponentToSpec()
                                       # - addWebserverComponentToSpec()
                                       # - addRedisComponentToSpec()
                                       # - addPgBouncerComponentToSpec()
                                       # - addStatsdComponentToSpec()
  src/lib/constants/index.js           # DEPLOYMENT_MODE, operator CRD constants
  src/workers/
    deployment-upserted-for-create/    # Routes to operator path when mode=operator
    deployment-upserted-for-update/    # Routes to operator path when mode=operator
    deployment-deleted/                # Routes to operator delete when mode=operator
    deployment-image-update/           # Image update for operator deployments
    deployment-variables-updated/      # Env var update for operator deployments
  src/schema/mutation.js               # GraphQL upsertDeployment mutation
  src/resolvers/mutation/
    upsert-deployment/index.ts         # setDeploymentMode() default handling
  prisma/schema.prisma                 # Deployment.mode field
```

### What Needs To Be Done

- [ ] **Verify CRD spec matches current operator schema**: The operator's `v1beta1` types may have evolved since 0.37. Compare `getCRDSpecFromHelmValues()` output against `airflow-operator/apis/airflow/v1beta1/airflow_types.go`. Key areas:
  - Does it handle `APIServer` (Airflow 3.x) vs `Webserver` (Airflow 2.x)?
  - Does it include `EventScheduler` component (AstroExecutor only)?
  - Are new fields like `AstroAgentVersion` handled?
- [ ] **Fix MySQL probe config fallback**: The code at `index.js:250-272` calls `config.get("deployments.mode.operator.{component}.mysql.{probe}")` but these config paths have no defaults in the chart. Either:
  - Add defaults in houston-configmap.yaml (preferred), OR
  - Add fallback defaults in the operator index.js code
- [ ] **Verify PLX-254/PLX-280 config path changes**: The feature flag restructuring may have altered config paths the operator code depends on. Grep for all `config.get(...)` calls in `operator/index.js` and verify they match the current chart configmap output.
- [ ] **Test mode flow end-to-end**: Verify:
  1. GraphQL `upsertDeployment(mode: "operator")` sets mode correctly
  2. Worker picks up the correct mode from the database
  3. `createOrUpdateDeploymentForOperatorMode()` generates valid CRD spec
  4. gRPC `ApplyCustomResource` call to commander succeeds
  5. Delete flow works via `DeleteCustomResource`
- [ ] **Verify DAG-only deployment**: The operator index.js generates K8s manifests for DAG-only deployments. Verify this code path works with the current DAG server images.
- [ ] **Check error handling**: The create worker checks for `COMMANDER_CUSTOM_RESOURCE_APPLIED` response. Verify commander returns this exact string. Also check `isObjectModificationError()` handling for race conditions.
- [ ] **Database migration**: Verify the `mode` column exists in the deployment table for 2.0. Check if prisma migrations are needed.

---

## 3. Commander (`commander` repo)

### What Exists

| Component | Location | Status |
|-----------|----------|--------|
| gRPC proto (Apply) | `_proto/custom_resource.proto` -> `ApplyCustomResourceRequest` | Present |
| gRPC proto (Delete) | `_proto/custom_resource.proto` -> `DeleteCustomResourceRequest` | Present |
| Service definition | `_proto/commander.proto` -> `ApplyCustomResource()`, `DeleteCustomResource()` | Present |
| API handler | `api/custom_resource.go` | Present |
| K8s implementation | `kubernetes/custom_resource.go` | Present |

### Key Files

```
commander/
  _proto/
    custom_resource.proto              # ApplyCustomResourceRequest/Response, DeleteCustomResourceRequest/Response
    commander.proto                    # Service methods: ApplyCustomResource, DeleteCustomResource
  api/
    custom_resource.go                 # gRPC handler
  kubernetes/
    custom_resource.go                 # K8s client implementation
                                       # - Namespace label merge
                                       # - Secret sync from platform namespace
                                       # - Secret/ConfigMap creation from request
                                       # - CRD spec parse + apply
                                       # - K8s manifest apply (DAG-only)
                                       # - Cleanup cron job creation
```

### What Needs To Be Done

- [ ] **Fix imagePullSecret assignment bug**: At `kubernetes/custom_resource.go:1228`, the code appears to set `image` instead of `imagePullSecret` when extracting from CRD options. Verify and fix.
- [ ] **Verify K8s client compatibility**: The `ApplyCustomResource` implementation uses unstructured client to apply CRDs. Verify this works with current controller-runtime / client-go versions in the 2.0 commander.
- [ ] **Verify secret sync for 2.0**: The secret synchronization (lines 1153-1182) copies platform secrets to the deployment namespace. Verify:
  - Houston JWT certificate secret name matches 2.0 convention
  - TLS certificate secret name matches
  - Registry auth secret is included
  - Silent failure on sync errors is acceptable or needs hardening
- [ ] **Verify CRD apply flow**: Test that commander can:
  1. Parse a valid Airflow CRD JSON spec
  2. Apply it to the cluster via unstructured client
  3. Return `COMMANDER_CUSTOM_RESOURCE_APPLIED` response
  4. Handle already-exists (update) vs not-exists (create)
- [ ] **Verify delete flow**: Test `DeleteCustomResource` properly removes the Airflow CR and cleans up associated resources.
- [ ] **Verify cleanup cron job**: The implementation creates a cleanup cron job. Verify this is still needed and works correctly in 2.0.

---

## 4. APC UI (`apc-ui` repo)

### What Exists

| Component | Location | Status |
|-----------|----------|--------|
| Mode constants | `src/utils/constants.ts:123-131` | Present (`helm`, `operator`) |
| Mode field component | `src/components/DeploymentUpdateForm/parts/DeploymentModeField/` | Present |
| Executor restrictions | `src/components/DeploymentUpdateForm/parts/ExecutorField/ExecutorField.tsx` | Present (no LocalExecutor for operator) |
| DAG deploy restrictions | `src/components/DeploymentUpdateForm/DagDeploymentSection/DagDeploymentSection.tsx` | Present (no NFS/GitSync for operator) |
| Metrics display | `src/components/DeploymentMetrics.tsx` | Present |

### What Needs To Be Done

- [ ] **Verify mode field wiring**: Confirm `DeploymentModeField` passes the mode value through to the `upsertDeployment` GraphQL mutation.
- [ ] **Check 2.0 UI redesign impact**: If the deployment creation/update flow was redesigned for 2.0, verify the operator mode field still renders correctly.
- [ ] **Review feature restrictions**: Verify that operator-mode restrictions are still accurate for the current operator version:
  - LocalExecutor disabled (still true?)
  - NFS/GitSync disabled (still true? operator now supports these?)
  - Extra Capacity disabled (still true?)
- [ ] **Verify feature flag gating**: The mode selection should only appear when `deployments.mode.operator.enabled` is true in houston config. Verify this conditional.
- [ ] **Update "experimental" label**: Decide if operator mode is still "experimental" in 2.0 or should be labeled differently.

---

## 5. Airflow Operator (`airflow-operator` repo)

### What Exists

The operator is a standalone Kubernetes operator (kubebuilder-based) with:
- 13 CRDs under `airflow.apache.org/v1beta1`
- 11 controllers (Airflow, Webserver, APIServer, Scheduler, DAGProcessor, Worker, Triggerer, EventScheduler, Redis, Postgres, StatsD, PgBouncer, RBAC)
- Validating + mutating webhooks
- Helm chart for standalone deployment
- Support for Airflow 2.x and 3.x
- Multiple executors: CeleryExecutor, KubernetesExecutor, LocalExecutor, AstroExecutor

### Key Files

```
airflow-operator/
  main.go                              # Entry point, feature flags (--airgapped, --openshift, --keda)
  config.yaml                          # Runtime config (systemRegistry, environment, agentTokenIssuer)
  apis/airflow/v1beta1/                # CRD type definitions
    airflow_types.go                   # Root Airflow CR spec
    airflow_webhook.go                 # Validation/defaulting webhook
  controllers/airflow/
    airflow_controller.go              # Main reconciler (137KB)
    controller_util.go                 # Shared utilities (60KB)
  internal/airflow/                    # Component resource builders
  pkg/
    constants/                         # Image defaults, executor types, labels
    versions/                          # Runtime version fetching from updates.astronomer.io
  config/
    crd/bases/                         # Generated CRD YAML definitions
    samples/                           # Example Airflow CRs
  helm/                                # Standalone Helm chart
  integration-tests/                   # pytest-bdd integration tests
```

### What Needs To Be Done

- [ ] **Verify config.yaml APC compatibility**: The operator's `config.yaml` includes `SystemRegistry`, `Environment`, `AgentTokenIssuer`, `AgentTokenJWKS`. For APC deployments:
  - `SystemRegistry` should point to the APC-configured registry (not the default `quay.io/astronomer`)
  - `Environment` may need to be configurable per APC installation
  - `AgentTokenIssuer`/`AgentTokenJWKS` are Astro-specific — verify they're optional for APC
- [ ] **Verify image availability**: Ensure `quay.io/astronomer/airflow-operator-controller` is published and accessible from customer environments (including air-gapped).
- [ ] **Test CRD pickup from Commander**: When commander applies an Airflow CR, the operator should detect it via watch and reconcile. Test this end-to-end.
- [ ] **Verify RBAC alignment**: The operator creates its own RBAC (ClusterRole). Commander also creates RBAC for the deployment namespace. Verify these don't conflict.
- [ ] **Test MySQL backend**: The operator supports MySQL as metadata DB. Verify MySQL-backed deployments work with the CRD spec Houston generates.
- [ ] **OpenShift support**: The operator has `--openshift` flag but it's listed as a gap. Determine current status and what's needed for APC OpenShift customers.
- [ ] **Version compatibility**: Decide on operator version to ship. Current chart: 1.5.2, repo HEAD: 1.6.0-rc1.

---

## 6. APC Airflow (`apc-airflow` repo)

### What Exists

The `apc-airflow` chart is the Helm chart used for Helm-mode Airflow deployments. When operator mode is used, the operator manages Airflow independently.

### What Needs To Be Done

- [ ] **Verify no shared dependencies**: Confirm that operator-mode deployments don't rely on any resources created by the apc-airflow chart.
- [ ] **Check shared config/secrets patterns**: If apc-airflow creates any secrets or configmaps that the operator expects (e.g., Fernet key format, DB connection string format), document the expected formats.
- [ ] **DAG deployment compatibility**: If apc-airflow's DAG deployment mechanism is shared with operator mode, verify compatibility.

---

## 7. Astro CLI (`astro-cli` repo)

### What Exists

CLI support for operator mode was listed as **unsupported** in 0.37 release notes.

### What Needs To Be Done

- [ ] **Determine scope**: Is CLI support for operator mode in scope for APC 2.0? If yes:
  - Add `--mode operator` flag to `astro deployment create` and `astro deployment update`
  - Verify `astro deploy` (DAG deployment) works with operator deployments
  - Add operator-specific deployment info in `astro deployment inspect`
- [ ] **If not in scope**: Document this as a known limitation for 2.0.

---

## Cross-Cutting Concerns

### Secrets Management
When an operator deployment is created, commander syncs platform secrets to the deployment namespace:
- Houston JWT certificate (for API authentication)
- TLS certificates
- Registry auth secrets (for image pulling)
- Airflow metadata DB connection string
- Fernet key

**Action needed:** Verify all secret names match 2.0 conventions. The secret sync in `commander/kubernetes/custom_resource.go` has silent failures that could leave deployments broken.

### Metrics Pipeline
Flow: Airflow pods -> StatsD -> kube-state-metrics -> Prometheus -> Grafana

**Action needed:** Verify the prometheus scrape config label filter `astronomer_io_platform_release` matches what the operator sets on its managed pods.

### Database Support
Houston generates different CRD specs for PostgreSQL (with PgBouncer) and MySQL (without PgBouncer, with custom probes).

**Action needed:** MySQL probe config is missing from the Houston configmap. This is a P0 blocker for MySQL-backed operator deployments.

### Airflow 3.x Support
The operator supports both Airflow 2.x (Webserver) and 3.x (APIServer). Houston's CRD generation needs to handle both based on the runtime version.

**Action needed:** Verify `getCRDSpecFromHelmValues()` correctly routes to Webserver vs APIServer based on Airflow version.
