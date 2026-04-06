# Airflow Operator in APC 2.0 — Gap Analysis

**Linear Project:** [Install APC using an Operator](https://linear.app/astronomer/project/install-apc-using-an-operator-96722e2d8488)
**Last Updated:** 2026-04-06

---

## Priority Definitions

| Priority | Meaning |
|----------|---------|
| **P0** | Blocks POC / Milestone 1 — must be resolved before basic operator deployment works |
| **P1** | Blocks Feature Validation / Milestone 2 — needed for feature parity testing |
| **P2** | Blocks GA / Milestone 4 — must be resolved before shipping to customers |
| **P3** | Nice to have — can ship without, address in future releases |

## Effort Definitions

| Size | Meaning |
|------|---------|
| **S** | < 1 week, single codebase, well-scoped |
| **M** | 1-2 weeks, may span 2 codebases |
| **L** | 2-4 weeks, complex changes, design needed |
| **XL** | 4+ weeks, cross-team, significant design |

---

## Gap Summary

| # | Gap | Priority | Effort | Owner | Codebase |
|---|-----|----------|--------|-------|----------|
| 1 | [Houston missing MySQL probe config](#gap-1) | P0 | S | APC | astronomer, houston-api |
| 2 | [Airflow 3.x support in CRD generation](#gap-2) | P0 | M | APC / Operator | houston-api |
| 3 | [Operator image version mismatch](#gap-3) | P0 | S | APC | astronomer |
| 4 | [Commander imagePullSecret bug](#gap-4) | P1 | S | APC | commander |
| 5 | [Silent secret sync failures](#gap-5) | P1 | S | APC | commander |
| 6 | [Disabling SA / Role / RoleBindings](#gap-6) | P1 | M | Operator | airflow-operator |
| 7 | [Removal of cluster roles/bindings](#gap-7) | P2 | L | Operator | airflow-operator |
| 8 | [Platform-level Network Policy](#gap-8) | P1 | M | Operator / APC | airflow-operator, astronomer |
| 9 | [PlatformNodePool (pod separation)](#gap-9) | P2 | M | Operator | airflow-operator |
| 10 | [DAGs server](#gap-10) | P1 | L | Operator | airflow-operator |
| 11 | [DAG deployment method](#gap-11) | P1 | M | APC / Operator | houston-api, airflow-operator |
| 12 | [Git sync](#gap-12) | P2 | M | Operator | airflow-operator |
| 13 | [Resource Quota Mechanism](#gap-13) | P2 | M | APC | astronomer, houston-api |
| 14 | [OpenShift integration (First Class)](#gap-14) | P2 | XL | Operator | airflow-operator |
| 15 | [Enabling/Disabling Triggerer](#gap-15) | P1 | S | Operator | airflow-operator |
| 16 | [MySQL liveness/readiness probes](#gap-16) | P1 | S | APC | astronomer |
| 17 | [Celery Flower UI](#gap-17) | P3 | S | Operator | airflow-operator |
| 18 | [CLI support for operator mode](#gap-18) | P2 | M | APC | astro-cli |
| 19 | [Laminar auth coupling](#gap-19) | Info | - | Operator | airflow-operator |

---

## Detailed Gap Analysis

### Gap 1: Houston Missing MySQL Probe Config {#gap-1}

**Description:** Houston's operator code reads MySQL-specific probe configurations from `config.get("deployments.mode.operator.{component}.mysql.{probe}")`, but the Astronomer Helm chart's Houston configmap (`houston-configmap.yaml:99-101`) only passes `deployments.mode.operator.enabled`. The MySQL probe paths have no values.

**Root Cause:** APC-side. The chart configmap template was not updated to include MySQL probe defaults when the operator feature was originally shipped.

**Impact:** MySQL-backed operator deployments will fail or have no health checks. This affects customers using MySQL metadata databases (e.g., some enterprise requirements).

**Remediation Path:**
1. Add MySQL probe defaults to `astronomer/charts/astronomer/templates/houston/houston-configmap.yaml` under the `mode.operator` section
2. Define default values for scheduler, workers, triggerer, and webserver MySQL probes
3. Reference the probe configurations from `houston-api/src/lib/deployments/operator/index.js:250-272`

**Effort:** S
**Priority:** P0 — blocks MySQL operator deployments entirely

---

### Gap 2: Airflow 3.x Support in CRD Generation {#gap-2}

**Description:** The operator supports both Airflow 2.x (Webserver component) and 3.x (APIServer component). Houston's CRD spec generation (`getCRDSpecFromHelmValues()`) may not handle this distinction correctly.

**Root Cause:** Both APC and Operator. The operator added Airflow 3.x support (APIServer, EventScheduler) after the 0.37 release. Houston's CRD generation needs to be updated to conditionally include APIServer vs Webserver based on runtime version.

**Impact:** Operator deployments using Airflow 3.x runtime versions will fail or be misconfigured.

**Remediation Path:**
1. In `houston-api/src/lib/deployments/operator/index.js`, update `getCRDSpecFromHelmValues()` to:
   - Detect Airflow version from runtime version
   - Include `apiServer` spec for Airflow >= 3.0
   - Include `webserver` spec for Airflow < 3.0
   - Optionally include `eventScheduler` for AstroExecutor
2. Coordinate with operator team on exact version boundary
3. Update the operator's `airflow_types.go` type definitions if needed

**Effort:** M
**Priority:** P0 — Airflow 3.x is the current default for new deployments

---

### Gap 3: Operator Image Version Mismatch {#gap-3}

**Description:** The Astronomer chart's airflow-operator subchart (`charts/airflow-operator/values.yaml`) uses image tag `1.5.2`, while the operator repo is at `1.6.0-rc1`.

**Root Cause:** APC-side. Chart not updated to latest operator release.

**Impact:** Customers may miss bug fixes and features from newer operator versions.

**Remediation Path:**
1. Coordinate with operator team on a stable release for APC 2.0
2. Update `charts/airflow-operator/values.yaml` image tag
3. Sync CRD definitions in `charts/airflow-operator/templates/crds/` with the chosen version

**Effort:** S
**Priority:** P0 — must be resolved for any operator deployment

---

### Gap 4: Commander imagePullSecret Assignment Bug {#gap-4}

**Description:** In `commander/kubernetes/custom_resource.go:1228`, the code appears to assign a value to the `image` variable instead of `imagePullSecret` when extracting from the CRD spec options.

**Root Cause:** APC-side. Bug in commander code.

**Impact:** Operator-managed pods in namespaces requiring image pull secrets may fail to pull images.

**Remediation Path:**
1. Verify the bug exists (read `kubernetes/custom_resource.go:1225-1230`)
2. Fix the variable assignment
3. Add unit test for image pull secret extraction

**Effort:** S
**Priority:** P1 — affects private registry deployments

---

### Gap 5: Silent Secret Sync Failures {#gap-5}

**Description:** When commander's `ApplyCustomResource` syncs platform secrets to the deployment namespace (`kubernetes/custom_resource.go:1153-1182`), errors only log warnings and don't block deployment.

**Root Cause:** APC-side. Intentional design choice ("don't block deployment"), but the consequences can be severe.

**Impact:** Operator deployments may be created without:
- Houston JWT certificates (API auth fails)
- TLS certificates (HTTPS broken)
- Registry auth secrets (image pulls fail)

This produces hard-to-diagnose failures.

**Remediation Path:**
1. Classify secrets as critical (must-have) vs optional
2. Fail the deployment if critical secrets (JWT cert, registry auth) fail to sync
3. Continue with warning for optional secrets
4. Add better logging with secret names and failure reasons

**Effort:** S
**Priority:** P1 — silent failures cause significant debugging overhead

---

### Gap 6: Disabling SA / Role / RoleBindings {#gap-6}

**Description:** In Helm-mode APC deployments, customers can disable ServiceAccount, Role, and RoleBinding creation (using their own pre-provisioned RBAC). The operator always creates these resources.

**Root Cause:** Operator-side. The operator's RBAC controller always reconciles SA/Role/RoleBinding resources.

**Impact:** Customers with strict RBAC policies who pre-provision their own ServiceAccounts cannot use operator mode.

**Remediation Path:**
1. Add a field to the Airflow CRD spec: `rbac.create: false` (or similar)
2. Update the RBAC controller to skip creation when disabled
3. Update Houston CRD generation to pass the flag through
4. Document required pre-provisioned resources

**Effort:** M
**Priority:** P1 — required by enterprise customers (Ford, RBC)

---

### Gap 7: Removal of Cluster Roles/Bindings {#gap-7}

**Description:** The Helm approach allows deployments without ClusterRoles. The operator itself requires ClusterRoles for CRD management and webhook registration, making it impossible to run in environments that prohibit ClusterRoles.

**Root Cause:** Operator-side. Fundamental architecture constraint — CRDs and admission webhooks are cluster-scoped K8s resources.

**Impact:** Customers in environments with strict cluster-level RBAC restrictions cannot use the operator.

**Remediation Path:**
- This is a fundamental constraint of the Kubernetes operator pattern
- CRDs and webhooks are inherently cluster-scoped
- Options:
  1. **Accept the constraint** — document that operator mode requires ClusterRoles for the operator itself (but deployment namespaces can use namespace-scoped roles)
  2. **Namespace-scoped mode** — some operators support a "namespace-scoped" mode where CRDs are pre-installed by cluster admins and the operator only watches specific namespaces (the operator already supports `--namespaces` flag)
- Recommendation: Document the constraint and provide a "minimal ClusterRole" template that cluster admins can pre-approve

**Effort:** L (if implementing namespace-scoped mode); S (if documenting the constraint)
**Priority:** P2 — can be addressed with documentation for GA

---

### Gap 8: Platform-level Network Policy {#gap-8}

**Description:** In Helm mode, APC creates comprehensive NetworkPolicies for all Airflow components (scheduler, webserver, workers, etc.). The operator only creates NetworkPolicies for StatsD and PgBouncer (`enableNetworkPolicy` flag), leaving other components without network isolation.

**Root Cause:** Operator-side. The operator's NetworkPolicy implementation is incomplete.

**Impact:** Airflow pods in operator deployments lack network isolation. Pods can communicate freely within the namespace, which may not meet enterprise security requirements.

**Remediation Path:**
1. Add NetworkPolicy support to the operator for all components:
   - Scheduler: allow ingress from workers, webserver
   - Webserver: allow ingress from nginx/ingress
   - Workers: allow ingress from scheduler, egress to metadata DB
   - Redis: allow ingress from scheduler, workers
2. Add a CRD field: `networkPolicy.enabled` and `networkPolicy.rules`
3. Update Houston CRD generation to pass network policy config

**Effort:** M
**Priority:** P1 — required by enterprise security policies

---

### Gap 9: PlatformNodePool (Pod Separation) {#gap-9}

**Description:** In Helm mode, Airflow pods and Astronomer platform pods can be separated onto different node pools via `global.platformNodePool`. The operator doesn't support this separation.

**Root Cause:** Operator-side. NodeSelector/Affinity/Tolerations need to be passed through the CRD spec to operator-managed pods.

**Impact:** In multi-tenant environments, Airflow workloads may compete with platform components for resources.

**Remediation Path:**
1. Verify if the operator already supports `nodeSelector`/`affinity`/`tolerations` in component specs
2. If not, add these fields to all component specs in the CRD
3. Update Houston CRD generation to pass node pool configuration

**Effort:** M
**Priority:** P2 — important for production but not a blocker for POC/validation

---

### Gap 10: DAGs Server {#gap-10}

**Description:** APC supports a DAGs server component for DAG-only deployments (where DAGs are uploaded without rebuilding the image). The operator doesn't have native support for the DAGs server component.

**Root Cause:** Operator-side. The DAGs server is an APC-specific component, not part of the upstream Apache Airflow architecture.

**Impact:** DAG-only deployment method may not work properly with operator mode.

**Remediation Path:**
1. Determine if the DAGs server should be:
   a. Managed by the operator as a new component type, OR
   b. Deployed as a separate K8s resource by Commander alongside the Airflow CRD
2. If (a): Add DAGs server component to operator CRD and controller
3. If (b): Update Commander's `ApplyCustomResource` to deploy DAGs server resources via k8sManifests
4. Update Houston's DAG-only deployment code to generate the correct spec

**Effort:** L
**Priority:** P1 — DAG-only deploy is a core APC feature

---

### Gap 11: DAG Deployment Method {#gap-11}

**Description:** The operator doesn't natively support the APC DAG deployment methods (image-based vs DAG-only). Houston generates K8s manifests for DAG-only deployments and passes them via `k8sManifests` in the `ApplyCustomResource` request, but this is a workaround, not native operator support.

**Root Cause:** Both. The operator manages Airflow images via `spec.image`, but the APC DAG deployment mechanism (DAG server, DAG processor, sidecar sync) requires additional resources.

**Impact:** DAG deployment workflows may be fragile or partially broken.

**Remediation Path:**
1. Verify the current `k8sManifests` approach works end-to-end
2. If not, work with the operator team to add a `dagDeployment` section to the CRD spec
3. Update Houston's operator code to use the native approach

**Effort:** M
**Priority:** P1 — core workflow

---

### Gap 12: Git Sync {#gap-12}

**Description:** Git-sync based DAG deployment (sync DAGs from a Git repository) is not supported by the operator. This was also listed as unsupported in 0.37.

**Root Cause:** Operator-side. The operator doesn't include a git-sync sidecar in its component specs.

**Impact:** Customers using git-sync based DAG deployment workflows cannot use operator mode.

**Remediation Path:**
1. Add git-sync sidecar support to the operator's scheduler and worker specs
2. Add CRD fields for git repo URL, branch, sync interval, credentials
3. Update Houston CRD generation to pass git-sync configuration

**Effort:** M
**Priority:** P2 — alternative deployment methods (image-based, DAG-only) exist

---

### Gap 13: Resource Quota Mechanism {#gap-13}

**Description:** In Helm mode, APC enforces resource quotas per deployment namespace (CPU/memory limits). The operator doesn't enforce or create K8s ResourceQuotas.

**Root Cause:** APC-side. Commander creates ResourceQuotas in Helm mode; this logic doesn't exist for operator mode.

**Impact:** Without resource quotas, a single deployment could consume excessive cluster resources.

**Remediation Path:**
1. Have Commander create K8s ResourceQuota in the deployment namespace as part of `ApplyCustomResource`
2. Or: Add resource quota support to the operator CRD
3. Update Houston to calculate and pass quota values

**Effort:** M
**Priority:** P2 — important for multi-tenant production environments

---

### Gap 14: OpenShift Integration (First Class) {#gap-14}

**Description:** The operator has an `--openshift` flag for basic OpenShift support, but it's not considered "First Class." OpenShift has specific requirements around SecurityContextConstraints (SCCs), Routes (instead of Ingresses), and restricted security contexts.

**Root Cause:** Operator-side. OpenShift support needs hardening.

**Impact:** Customers running APC on OpenShift (e.g., some financial institutions) cannot use operator mode.

**Remediation Path:**
1. Audit all operator-created resources for OpenShift compatibility:
   - SecurityContext must be compatible with `restricted-v2` SCC
   - Routes instead of or in addition to Ingresses
   - Non-root UIDs, no privilege escalation
2. Test on OpenShift 4.x cluster
3. Add OpenShift-specific CI pipeline
4. Document OpenShift-specific configuration

**Effort:** XL — requires dedicated OpenShift environment and extensive testing
**Priority:** P2 — critical for enterprise customers but can be phased

---

### Gap 15: Enabling/Disabling Triggerer {#gap-15}

**Description:** In Helm mode, the triggerer component can be enabled/disabled. The operator doesn't support disabling the triggerer once enabled. Known bug from 0.37 — see [astronomer/issues#6857](https://github.com/astronomer/issues/issues/6857).

**Root Cause:** Operator-side. The operator always reconciles the triggerer if it was ever created.

**Impact:** Customers cannot disable the triggerer to save resources for deployments that don't use deferrable operators.

**Remediation Path:**
1. Fix the operator to respect `triggerer: null` or `triggerer.replicas: 0` in the CRD spec
2. Ensure the controller tears down triggerer resources when disabled
3. Update Houston CRD generation to support toggling

**Effort:** S
**Priority:** P1 — known bug, likely a small fix

---

### Gap 16: MySQL Liveness/Readiness Probes {#gap-16}

**Description:** MySQL-backed deployments need custom health check probes (scheduler and triggerer pods need to verify MySQL connectivity). These probe configurations are referenced in Houston's operator code but not provided by the chart configmap.

**Root Cause:** APC-side. Same root cause as Gap 1. The chart configmap doesn't include MySQL probe defaults.

**Impact:** MySQL-backed operator deployments may lack proper health checks, leading to pods not being restarted when MySQL connectivity is lost.

**Remediation Path:** Same as Gap 1 — add MySQL probe defaults to houston-configmap.yaml.

**Effort:** S
**Priority:** P1 — related to Gap 1

---

### Gap 17: Celery Flower UI {#gap-17}

**Description:** Celery Flower is a web-based monitoring tool for Celery workers. Helm-mode APC supports deploying Flower. The operator doesn't include Flower as a component.

**Root Cause:** Operator-side. Flower is not included as a CRD component.

**Impact:** No web-based Celery worker monitoring for operator deployments.

**Remediation Path:**
1. Add Flower as an optional component in the operator CRD
2. Or: Deploy Flower as a separate resource via Commander's `k8sManifests`

**Effort:** S
**Priority:** P3 — low usage, Grafana dashboards provide alternative monitoring

---

### Gap 18: CLI Support for Operator Mode {#gap-18}

**Description:** The Astro CLI (`astro-cli` repo) doesn't support creating or managing operator-mode deployments. This was listed as unsupported in 0.37.

**Root Cause:** APC-side. CLI was not updated for operator mode.

**Impact:** Developers must use the UI or direct GraphQL API to manage operator deployments. No CLI-based DAG deployment for operator mode.

**Remediation Path:**
1. Add `--mode operator` flag to `astro deployment create` and `astro deployment update`
2. Verify `astro deploy` works with operator deployments (DAG deployment)
3. Add operator deployment info in `astro deployment inspect`
4. Test end-to-end DAG deployment flow via CLI

**Effort:** M
**Priority:** P2 — important for developer experience but UI provides alternative

---

### Gap 19: Laminar Auth Coupling {#gap-19}

**Description:** The operator supports "Laminar" (event-driven execution mode), but its authentication is tightly coupled with Astro (Astro Hosted/Hybrid) authentication infrastructure. APC has its own auth system.

**Root Cause:** Operator-side. Laminar uses `agentTokenIssuer` and `agentTokenJWKS` which are Astro-specific.

**Impact:** Laminar/AstroExecutor features cannot be used in APC without auth decoupling.

**Remediation Path:**
- This is informational. Laminar support is not a requirement for APC 2.0.
- If needed in the future, the operator would need configurable auth providers.

**Effort:** -
**Priority:** Info — not in scope for APC 2.0

---

## Milestone Alignment

### Milestone 1: Environment Setup & Basic POC (target: 2026-04-18)
**Must resolve:** Gaps 1, 2, 3

### Milestone 2: Feature Validation (target: 2026-05-09)
**Must resolve:** Gaps 4, 5, 6, 8, 10, 11, 15, 16

### Milestone 3: Gap Analysis & Recommendation (target: 2026-05-23)
**Must have design docs for:** Gaps 7, 9, 12, 13, 14, 18

### Milestone 4: Development (target: 2026-07-11)
**Must implement:** All P2 gaps prioritized in Milestone 3

---

## Next Steps

1. **Immediately (this week):** Fix Gaps 1 and 3 (chart configmap + operator image version) — these are needed to start the POC
2. **This sprint:** Investigate Gap 2 (Airflow 3.x CRD generation) and determine scope
3. **Schedule with operator team:** Gaps 6, 8, 10, 15 — these require operator-side changes
4. **Design docs needed:** Gaps 7 (cluster roles constraint), 14 (OpenShift), 10 (DAGs server architecture)
