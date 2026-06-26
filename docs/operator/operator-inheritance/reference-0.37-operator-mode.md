# Reference — Operator Mode in APC 0.37

**Branches read:** `houston-api` @ `release-0.37`, `commander` @ `release-0.37`.
**Purpose:** A deep, citation-rich walkthrough of how operator-mode deployments work end-to-end in APC 0.37. Reference material for the Operator Inheritance project — informs every M2/M3 task in this folder.
**Companion docs:** [`00-overview.md`](00-overview.md), [`../01-codebase-changes.md`](../01-codebase-changes.md), [`../03-gap-analysis.md`](../03-gap-analysis.md).

> All `houston-api/...` and `commander/...` line citations are accurate against the `release-0.37` checkout. Numbers may drift on other branches.

---

## TL;DR

In 0.37, operator-mode looks structurally similar to helm-mode but with a different RPC:

- **Houston** is responsible for *all* spec generation. The CP service builds a complete Airflow CR JSON spec, plus the secrets and configmaps the CR needs, plus K8s YAML manifests for the DAG server.
- **Commander** is responsible for application. It receives the bundle over gRPC (`ApplyCustomResource`), syncs platform secrets, applies the request's secrets/configmaps, applies the CR via the unstructured/dynamic client, applies the DAG-server manifests, and schedules a cleanup CronJob.
- **The operator** (running independently) sees the CR appear and reconciles it into pods.

The CP/DP seam in 0.37 is roughly: "Houston knows the deployment's logical shape and turns it into raw K8s artefacts; Commander pushes those artefacts." Nothing on the DP side reasons about Airflow per se.

---

## High-level flow (create)

```mermaid
sequenceDiagram
    participant UI as Astro UI
    participant H as Houston (CP)
    participant W as Houston worker
    participant C as Commander (DP)
    participant K as Kubernetes API
    participant Op as airflow-operator

    UI->>H: upsertDeployment(mode="operator", ...)
    H->>H: resolver — validate + setDeploymentMode
    H->>H: Prisma upsert Deployment row
    H->>W: publish DEPLOYMENT_UPSERTED_FOR_CREATE
    W->>W: fetch helmValues + deployment
    W->>W: createOrUpdateDeploymentForOperatorMode()
    Note over W: build spec, secrets, configMaps, k8sManifests
    W->>C: gRPC ApplyCustomResource(spec, ...)
    C->>K: Ensure namespace + labels
    C->>K: Sync platform secrets (annotation-driven)
    C->>K: Create request Secrets + ConfigMaps
    C->>K: Apply Airflow CR (dynamic client)
    C->>K: Apply DAG-server manifests (if DAG-only)
    C->>K: Create cleanup CronJob
    C-->>W: "Custom Resource Applied Successfully"
    Op->>K: watch Airflow CR
    Op->>K: reconcile -> Scheduler, Workers, Webserver, ...
```

The update / image-update / vars-update flows replay the same Commander RPC (`ApplyCustomResource`). The delete flow uses `DeleteCustomResource`.

---

## Houston side

### Constants

[`houston-api/src/lib/constants/index.js`](../../../../houston-api/src/lib/constants/index.js):

| Constant | Lines | Value |
|---|---|---|
| `DEPLOYMENT_MODE` | 775–778 | `{ helm: "helm", operator: "operator" }` |
| `AIRFLOW_OPERATOR_DEFAULTS` | 805–810 | `{ apiVersion: "airflow.apache.org/v1beta1", kind: "Airflow", resourceGroup: "airflow.apache.org", resourceVersion: "v1beta1", resourcePlural: "airflows" }` |
| `COMMANDER_CUSTOM_RESOURCE_APPLIED` | 162–168 | `"Custom Resource Applied Successfully"` (response-success sentinel) |
| `COMMANDER_DEPLOYMENT_CREATED` / `COMMANDER_DEPLOYMENT_UPDATED` | 162–168 | Helm-mode counterparts |
| `WORKER_OPERATION_*` | 368–375 | Worker operation names: `create-deployment`, `update-deployment-config`, `update-deployment-image`, `update-deployment-variables`, `delete-deployment` |
| `UPSERT_DEPLOYMENT_FOR_CREATE` / `UPSERT_DEPLOYMENT_FOR_UPDATE` | 126–129 | Publisher names (`houston-upsert-deployment-for-create`, `..._update`) |
| `DEPLOYMENT_UPSERTED_FOR_CREATE` / `..._FOR_UPDATE` | 131–134 | Topic names (`houston.deployment.upserted.create`, `...update`) |
| `DEPLOYMENT_UPSERTED_ID_FOR_CREATE` / `..._UPDATE` | 136–139 | Worker subscription IDs |
| `DEPLOYMENT_UPSERTED_STARTED_FOR_CREATE` / `..._DEPLOYED_FOR_CREATE` | 147–148 | Status sub-topics |
| `DEPLOYMENT_DELETED` / `DEPLOYMENT_DELETED_ID` | 157–158 | Delete topic + worker ID |
| `DEPLOYMENT_IMAGE_UPDATED` / `..._ID` | 120–122 | Image-update topic + worker ID |
| `DEPLOYMENT_VARS_UPDATED` / `..._ID` | 171–173 | Env-vars-update topic + worker ID |

### GraphQL surface

The `upsertDeployment` mutation is defined at [`houston-api/src/schema/mutation.js:871-953`](../../../../houston-api/src/schema/mutation.js#L871-L953) (on 0.37). Args include `mode` of type `AllowedDeploymentModeValues` (the enum constructed from `DEPLOYMENT_MODE`), `executor`, `workers`, `scheduler`, `triggerer`, etc.

### Resolver

[`houston-api/src/resolvers/mutation/upsert-deployment/index.ts`](../../../../houston-api/src/resolvers/mutation/upsert-deployment/index.ts):

- **Line 59** — `setDeploymentMode(args)`: defaults `mode` to `DEPLOYMENT_MODE.helm` when not supplied.
- **Line 77** — on create, mode is set explicitly on the new record.
- **Line 85** — publishes the `started` event (`DEPLOYMENT_UPSERTED_STARTED_FOR_CREATE`).
- **Lines 172–173 / 205–209** — Prisma `upsert()` persists the row via `marshalDeploymentData`; `mode` is one of the persisted columns.
- **Lines 239–246** — creates the `DEPLOYMENT_ADMIN` role binding tying the requester to the new deployment.
- **Line 292** — publishes the main `DEPLOYMENT_UPSERTED_FOR_CREATE` (or `..._UPDATE`) event with payload `{ id, passwords, deploymentUpsertPurpose, environment variables }`.

### Worker — create

[`houston-api/src/workers/deployment-upserted-for-create/index.js`](../../../../houston-api/src/workers/deployment-upserted-for-create/index.js) (lines 63–291):

- Subscribed via pub/sub pattern (`pubSub(parent, publisherId, eventName, handler)` ~lines 49–53).
- **Line 103** — `updateChartVersion(id)` writes the resolved chart version back to the DB.
- **Line 209** — branch: `if (deployment.mode === DEPLOYMENT_MODE.operator)`.
- **Lines 210–218** — calls `createOrUpdateDeploymentForOperatorMode({ helmValues, namespace, namespaceLabels, releaseName, registryPassword, deployment, deploymentSecrets })`.
- **Lines 220–231** — else-branch: helm-mode → `commander.request("createDeployment", { ... })`.
- **Lines 243–245** — validates response message against `COMMANDER_CUSTOM_RESOURCE_APPLIED` (operator) / `COMMANDER_DEPLOYMENT_CREATED` (helm).

### Worker — update

[`houston-api/src/workers/deployment-upserted-for-update/index.js`](../../../../houston-api/src/workers/deployment-upserted-for-update/index.js) (lines 56–230):

- **Line 161** — same `deployment.mode === DEPLOYMENT_MODE.operator` branch.
- **Lines 162–169** — calls `createOrUpdateDeploymentForOperatorMode()` (same function as create — full re-emit, not a diff).
- **Lines 171–179** — helm-mode → `commander.request("updateDeployment", ...)`.
- **Lines 184–185** — validates response against `COMMANDER_CUSTOM_RESOURCE_APPLIED` / `COMMANDER_DEPLOYMENT_UPDATED`.

### Worker — image update

[`houston-api/src/workers/deployment-image-update/index.js`](../../../../houston-api/src/workers/deployment-image-update/) — uses an internal `commanderUpdateDeployment()` helper that runs the same operator-mode branch and re-invokes `createOrUpdateDeploymentForOperatorMode()`. Functionally identical to the update worker except triggered by image-update events.

### Worker — env vars updated

[`houston-api/src/workers/deployment-variables-updated/index.js`](../../../../houston-api/src/workers/deployment-variables-updated/) — same operator branch, calls `createOrUpdateDeploymentForOperatorMode()` with the updated env vars folded in. Response validated against `COMMANDER_CUSTOM_RESOURCE_APPLIED`.

### Worker — delete

[`houston-api/src/workers/deployment-deleted/index.js`](../../../../houston-api/src/workers/deployment-deleted/index.js):

- **Lines 124–132** — `getDeploymentByID()` fetches the row, selecting `mode`.
- **Line 157** — branch on `deployment.mode === DEPLOYMENT_MODE.operator`.
- **Lines 158–161** — calls `deleteDeploymentForOperatorMode({ namespace, releaseName })`.
- **Lines 163–168** — helm-mode → `commander.request("deleteDeployment", ...)`.
- **Line 104** — hard-deletes the deployment row (`deleteOne(prisma, "deployment", { where: { id } })`) when the hard-delete flag is on.
- **Line 52** — reads `workers.deleteDeploymentConfig.retryCount` from config for the retry loop.

### Orchestrator — `createOrUpdateDeploymentForOperatorMode()`

[`houston-api/src/lib/deployments/operator/index.js`](../../../../houston-api/src/lib/deployments/operator/index.js) lines 1274–1357 (release-0.37 numbering):

1. **Line 1285** — `getSecretsForOperatorMode()` builds the secrets array (§Secrets below).
2. **Line 1293** — `getCRDSpecFromHelmValues()` builds the CR `.spec` object (§Spec below).
3. **Line 1301** — `getConfigMapsForOperatorMode()` builds the configmaps array (§ConfigMaps below).
4. **Line 1308** — `generateK8sManifests()` builds the DAG-server K8s YAML (§DAG manifests below).
5. **Lines 1341–1356** — gRPC call:

```js
return commander.request("ApplyCustomResource", {
  spec: JSON.stringify(airflowSpecForOperator),
  secrets,
  configMaps,
  k8sManifests: JSON.stringify(k8sManifests),
  apiVersion:  AIRFLOW_OPERATOR_DEFAULTS.apiVersion,
  correlationId: getCorrelationId(),
  kind: AIRFLOW_OPERATOR_DEFAULTS.kind,
  name: releaseName,
  namespace,
  namespaceLabels,
  resourceGroup: AIRFLOW_OPERATOR_DEFAULTS.resourceGroup,
  resourceVersion: AIRFLOW_OPERATOR_DEFAULTS.resourceVersion,
  resourcePlural: AIRFLOW_OPERATOR_DEFAULTS.resourcePlural,
  dagDeploymentType: get(deployment, "config.dagDeployment.type"),
});
```

### Orchestrator — `deleteDeploymentForOperatorMode()`

Same file, lines 1363–1377:

```js
return commander.request("DeleteCustomResource", {
  apiVersion:  AIRFLOW_OPERATOR_DEFAULTS.apiVersion,
  kind:        AIRFLOW_OPERATOR_DEFAULTS.kind,
  name:        releaseName,
  namespace,
  resourceGroup:   AIRFLOW_OPERATOR_DEFAULTS.resourceGroup,
  resourceVersion: AIRFLOW_OPERATOR_DEFAULTS.resourceVersion,
  resourcePlural:  AIRFLOW_OPERATOR_DEFAULTS.resourcePlural,
});
```

### CRD spec construction — `getCRDSpecFromHelmValues()`

Same file, lines 682–694. Three-step build:

```js
function getCRDSpecFromHelmValues({ helmValues, releaseName, deployment, envVars, deploymentSecrets }) {
  const spec = {};
  addAirflowComponentsToSpec({ spec, helmValues, releaseName, deployment });   // line 618
  addMiscellaneousComponentsToSpec({ spec, helmValues, releaseName });          // line 209
  addDeploymentEnvVarsToSpec({ spec, envVars, releaseName, deploymentSecrets });
  return spec;
}
```

Note: **helm values are passed in by the worker** — `operator/index.js` does not fetch them. The worker reads them from the Helm release earlier in the pipeline.

#### Components added in `addAirflowComponentsToSpec()`

| Component | Helper | Line | Notes |
|---|---|---|---|
| `spec.executor` | inline | 624 | `get(helmValues, "airflow.executor")` |
| `spec.scheduler` | `addSchedulerComponentToSpec()` | 466 / 635 | Sets executor, runtime version, image, registry secret. Disables DAG processor (separate component in this version's CRD). |
| `spec.workers[]` | `addWorkersComponentToSpec()` | 483 / 636 | Wraps in array. Disables KEDA autoscaling. |
| `spec.triggerer` | `addTriggererComponentToSpec()` | 508 / 637 | Bare component. |
| `spec.webserver` | `addWebserverComponentToSpec()` | 530 / 638 | Volumes + ingress config (AF 2.x only — there is no AF 3.x `apiServer` branch in 0.37). |

#### Components added in `addMiscellaneousComponentsToSpec()` (line 209)

| Component | Helper | Line |
|---|---|---|
| `spec.redis` | `addRedisComponentToSpec()` | 188 / 228 |
| Elasticsearch env wiring | `addElasticSearchComponentToSpec()` | 59 / 229 |
| Statsd env wiring | `addStatsdComponentToSpec()` | 111 / 230 |
| PgBouncer | `addPgBouncerComponentToSpec()` | 142 / 231 |

#### Resources & replicas (per-component)

`addBaseComponentToSpec()` at [`operator/index.js`](../../../../houston-api/src/lib/deployments/operator/index.js) lines 363–443 reads `helmValues.airflow.{component}.resources.{requests,limits}.{cpu,memory}` and writes them under `podTemplateSpec.spec.containers[0].resources`. Replicas are emitted only when present in helm values (lines 425–427). Ephemeral-storage requests/limits supported.

#### MySQL probe injection

`addMysqlSpecificProbesToBaseComponent()` at lines 234–274. Called from `addBaseComponentToSpec()` (lines 461–462) when MySQL is enabled. Reads:

```js
get(config, `deployments.mode.operator.${componentName}.mysql.startupProbe`)
get(config, `deployments.mode.operator.${componentName}.mysql.livenessProbe`)
get(config, `deployments.mode.operator.${componentName}.mysql.readinessProbe`)
```

Each, if present, is set onto `${componentName}.podTemplateSpec.spec.containers[0].{startup,liveness,readiness}Probe`. **The chart configmap doesn't populate these paths** — this is the root of [`../03-gap-analysis.md`](../03-gap-analysis.md) Gap 1 / Gap 16.

#### Executor branching

The operator-mode `airflow.cfg` ConfigMap unconditionally sets `EXECUTOR = KubernetesExecutor` (operator/index.js lines 747–791). The Python `airflow_local_settings.py` content rendered into a ConfigMap (line 911) branches on `conf.get('core', 'EXECUTOR')`. **There is no Celery vs Local vs Kubernetes branching in the CRD spec itself in 0.37 — operator-mode is effectively K8s-executor only.**

### Secrets — `getSecretsForOperatorMode()`

Lines 1144–1175. Returns an array of `{ name, data, type, annotations }` objects:

| Secret | Helper | Line | Condition |
|---|---|---|---|
| `${releaseName}-elasticsearch` | `addElasticSearchSecretToSecrets()` | 957 / 1152–1157 | `airflow.elasticsearch.enabled === true` and host set. Base64-encoded `http://user:pass@host:port`. |
| `${releaseName}-metadata` | `addDatabaseConnectionStringsToSecrets()` | 1010 / 1158–1162 | Metadata DB URI from `helmValues.airflow.data.metadataConnection`. |
| `${releaseName}-result-backend` | (same helper) | 1010 / 1158–1162 | Result-backend URI from `helmValues.airflow.data.resultBackendConnection` (prepended with `db+`). Falls back to `helmValues.airflow.extraSecrets`. |
| `${releaseName}-registry` | `addRegistrySecretToSecrets()` | 1082 / 1163–1168 | Only if no pre-existing private registry secret AND `registryPassword` is passed in. `.dockerconfigjson` with base64 `username:password`. |
| `${releaseName}-pgbouncer-connection` | `addPgBounderSecretToSecrets()` | 1125 / 1169 | MySQL-only — dummy stub (workaround for operator bug). |
| Caller-supplied | (no helper) | 1170–1173 | `deploymentSecrets` from the upsert flow. |

### ConfigMaps — `getConfigMapsForOperatorMode()`

Lines 1177–1194. Returns three configmaps:

| ConfigMap | Helper | Line | Contents |
|---|---|---|---|
| `${releaseName}-webserver-config` | `addWebserverConfigMapToConfigMaps()` | 696 / 1184 | Hardcoded `webserver_config.py` content from `WEBSERVER_CONFIGMAP_FOR_OPERATOR` constant. |
| `${releaseName}-airflow-config` | `addAirflowConfigMapToConfigMaps()` | 711 / 1185–1191 | Large INI: `[api]`, `[dag_deploy]`, `[astronomer]`, `[celery]`, `[celery_kubernetes_executor]`, `[core]`, `[elasticsearch]`, `[kubernetes]`, `[kubernetes_executor]`, `[kubernetes_secrets]`, `[logging]`, `[metrics]`, `[operators]`, `[scheduler]`, `[triggerer]`, `[webserver]`. Interpolates DAG-downloader config, worker resources, base domain, JWT settings. |
| `${releaseName}-airflow-local-settings` | `addAirflowLocalSettingsToConfigMaps()` | 807 / 1192 | Python source (starts line 812). Pod mutation hooks for K8s executor and KPO. Branches on executor type at line 911. |

### DAG-only deployment manifests

[`houston-api/src/lib/deployments/operator/manifests/dag-only-deploy/`](../../../../houston-api/src/lib/deployments/operator/manifests/dag-only-deploy/):

| Template | Resource generated |
|---|---|
| `dag-downloader-role.json.hbs` | `Role` for DAG downloader RBAC |
| `dag-downloader-rolebinding.json.hbs` | `RoleBinding` for the above |
| `dag-server-role.json.hbs` | `Role` for the DAG server |
| `dag-server-rolebinding.json.hbs` | `RoleBinding` for the above |
| `dag-server-serviceaccount.json.hbs` | `ServiceAccount` for the DAG server |
| `dag-server-service.json.hbs` | `Service` (ClusterIP / LoadBalancer) |
| `dag-server-ingress.json.json.hbs` | `Ingress` |
| `dag-server-statefulset.json.hbs` | `StatefulSet` |

`generateDagServerManifests()` at [`operator/index.js`](../../../../houston-api/src/lib/deployments/operator/index.js) lines 1203–1252 reads the folder via `processHBSTemplatesInFolder()` (line 1247–1250) and renders with handlebars values: `workspaceId, namespace, releaseName, registrySecretName, dagServerImage, dagServerImagePullPolicy, dagServerResources, platformReleaseName, platformNamespace, containerSecurityContext, podSecurityContext, persistenceEnabled, persistentVolumeClaimRetentionPolicy, dagServerAnnotations, dagServerIngressPath, tlsSecretName, ingressHost, ingressHosts`.

Only generated when `helmValues.dagDeploy.enabled === true`.

### Houston config keys consumed by the operator path

`config.get(...)` calls in or around `operator/index.js`:

| Path | Line | Purpose |
|---|---|---|
| `deployments.mode.operator.${componentName}.mysql.{startup,liveness,readiness}Probe` | 234–274 | MySQL probes (Gap 1 / Gap 16) |
| `deployments.subdomain` | 525 | Ingress host generation |
| `helm.baseDomain` | 721 | Ingress / configmap interpolation |
| `deployments.logHelmValues` | 1317 | Toggles helm-values logging during operator apply |

Plus per-worker:

| Path | Worker | Line |
|---|---|---|
| `nats.jetStreamEnabled` | deployment-upserted-for-create | 64 |
| `workers.deleteDeploymentConfig.retryCount` | deployment-deleted | 52 |

### Pub/Sub event table (operator-mode flows)

| Action | Resolver publishes | Subscribed by | Calls Commander |
|---|---|---|---|
| Create | `DEPLOYMENT_UPSERTED_STARTED_FOR_CREATE` → `DEPLOYMENT_UPSERTED_FOR_CREATE` | `deployment-upserted-for-create` worker (`DEPLOYMENT_UPSERTED_ID_FOR_CREATE`) | `ApplyCustomResource` |
| Update | `DEPLOYMENT_UPSERTED_STARTED_FOR_UPDATE` → `DEPLOYMENT_UPSERTED_FOR_UPDATE` | `deployment-upserted-for-update` worker (`DEPLOYMENT_UPSERTED_ID_FOR_UPDATE`) | `ApplyCustomResource` |
| Image update | `DEPLOYMENT_IMAGE_UPDATED` | `deployment-image-update` worker (`DEPLOYMENT_IMAGE_UPDATED_ID`) | `ApplyCustomResource` |
| Env vars update | `DEPLOYMENT_VARS_UPDATED` | `deployment-variables-updated` worker (`DEPLOYMENT_VARS_UPDATED_ID`) | `ApplyCustomResource` |
| Delete | `DEPLOYMENT_DELETED` | `deployment-deleted` worker (`DEPLOYMENT_DELETED_ID`) | `DeleteCustomResource` |

---

## gRPC contract

### Proto messages

[`commander/_proto/custom_resource.proto`](../../../../commander/_proto/custom_resource.proto):

```proto
// lines 9-25
message ApplyCustomResourceRequest {
  string spec = 1;                              // CRD JSON spec (Houston-generated)
  string namespace = 2;
  string apiVersion = 3;
  string kind = 4;
  string name = 5;
  string correlation_id = 7;
  repeated Label namespaceLabels = 8;
  repeated Annotation namespaceAnnotations = 9;
  string resourceGroup = 10;
  string resourceVersion = 11;
  string resourcePlural = 12;
  repeated Secret secrets = 13;
  repeated ConfigMap configMaps = 14;
  string k8sManifests = 15;                     // JSON array of K8s manifests for DAG-only
  string dagDeploymentType = 16;
}

// lines 27-29
message ApplyCustomResourceResponse {
  Result result = 1;
}

// lines 31-40
message DeleteCustomResourceRequest {
  string namespace = 1;
  string apiVersion = 2;
  string kind = 3;
  string name = 4;
  string correlation_id = 5;
  string resourceGroup = 6;
  string resourceVersion = 7;
  string resourcePlural = 8;
}

// lines 42-44
message DeleteCustomResourceResponse {
  Result result = 1;
}
```

[`commander/_proto/common.proto`](../../../../commander/_proto/common.proto) — helper types:

```proto
// Label (27-29)
message Label { string key = 1; string value = 2; }
// Annotation (32-35)
message Annotation { string key = 1; string value = 2; }
// Secret (38-43)
message Secret {
  string name = 1;
  map<string,string> data = 2;
  map<string,string> annotations = 3;
  string type = 4;                              // Opaque / kubernetes.io/tls / etc.
}
// ConfigMap (45-50)
message ConfigMap {
  string name = 1;
  map<string,string> data = 2;
  map<string,string> annotations = 3;
  repeated Label labels = 4;
}
// Result (52-55)
message Result { bool success = 1; string message = 2; }
```

### Service registration

[`commander/_proto/commander.proto`](../../../../commander/_proto/commander.proto):

```proto
// line 26
rpc ApplyCustomResource (ApplyCustomResourceRequest) returns (ApplyCustomResourceResponse) {}
// line 27
rpc DeleteCustomResource (DeleteCustomResourceRequest) returns (DeleteCustomResourceResponse) {}
```

---

## Commander side

### Handler (thin pass-through)

[`commander/api/custom_resource.go`](../../../../commander/api/custom_resource.go):

```go
// lines 8-10
func (s *Server) ApplyCustomResource(ctx context.Context, in *ApplyCustomResourceRequest) (*ApplyCustomResourceResponse, error) {
    return s.provisioner.ApplyCustomResource(in)
}
// lines 12-14
func (s *Server) DeleteCustomResource(ctx context.Context, in *DeleteCustomResourceRequest) (*DeleteCustomResourceResponse, error) {
    return s.provisioner.DeleteCustomResource(in)
}
```

No logging, error wrapping, or metric emission at this layer. All orchestration happens in the provisioner.

### Provisioner — `ApplyCustomResource`

[`commander/provisioner/kubernetes/kubernetes.go`](../../../../commander/provisioner/kubernetes/kubernetes.go) lines 488–624:

#### Step 1 — Namespace ensure (lines 500–505)

```go
err := k.kube.Namespace.Ensure(request.Namespace, namespaceLabels, namespaceAnnotations)
```

`Ensure()` lives at [`commander/kubernetes/namespace.go:120-156`](../../../../commander/kubernetes/namespace.go#L120-L156):

- Gates on `IsCommanderManageNamespaceResource()` (line 129).
- If true and namespace exists: JSON-patches labels/annotations (lines 130–148).
- If true and namespace missing: creates it (line 152), invoking `Create()` (line 92), which itself only applies labels if the flag is enabled (line 89).
- Tracks **astro-managed labels/annotations** in the namespace's own annotations so that adds and removes are idempotent (lines 160–188).
- Controlled by env var `COMMANDER_MANAGE_NAMESPACE_RESOURCE` (default true — see [`commander/config/config.go:31`](../../../../commander/config/config.go#L31)).

#### Step 2 — Platform secret sync (lines 507–537)

```go
allSecrets := k.kube.Secret.List(appConfig.PlatformNamespace)
for _, s := range allSecrets {
    if _, ok := s.Annotations[kubernetes.SecretsToSynchronizeAnnotation]; !ok {
        continue
    }
    err := k.kube.Secret.CreateOrUpdate(request.Namespace, ...)  // lines 527-532
}
```

- `SecretsToSynchronizeAnnotation = "astronomer.io/commander-sync"` ([`commander/kubernetes/secret.go:13`](../../../../commander/kubernetes/secret.go#L13)).
- Secrets so annotated in the platform namespace (Houston JWT, TLS chain, registry auth, Fernet key, DB connections) get copied into the deployment namespace.
- Errors **log a warning and continue** (silent failure pattern — see [`../03-gap-analysis.md`](../03-gap-analysis.md) Gap 5).

#### Step 3 — Apply request-payload secrets + configmaps (lines 539–559)

```go
for _, sec := range request.Secrets {
    k.kube.Secret.CreateOrUpdate(request.Namespace, sec.Name, sec.Data, sec.Type, sec.Annotations)
}
for _, cm := range request.ConfigMaps {
    k.kube.ConfigMap.CreateOrUpdate(request.Namespace, cm.Name, cm.Data, cm.Labels, cm.Annotations)
}
```

These are the secrets/configmaps Houston built in `getSecretsForOperatorMode()` / `getConfigMapsForOperatorMode()`.

#### Step 4 — Parse + apply the CR (lines 561–572)

```go
spec, err := utils.ParseJSON(request.Spec)             // line 562
err = k.kube.Resource.ApplyCustomResource(
    request.ResourceGroup,
    request.ResourceVersion,
    request.ResourcePlural,
    request.Namespace,
    request.Name,
    spec,
)
```

The dynamic apply lives at [`commander/kubernetes/custom_resource.go:18-49`](../../../../commander/kubernetes/custom_resource.go#L18-L49):

```go
gvr := schema.GroupVersionResource{Group: group, Version: version, Resource: plural}
obj := &unstructured.Unstructured{Object: map[string]interface{}{
    "apiVersion": fmt.Sprintf("%s/%s", group, version),
    "kind":       kind,
    "metadata":   map[string]interface{}{"name": name, "namespace": namespace},
    "spec":       spec,
}}
existing, err := dyn.Resource(gvr).Namespace(namespace).Get(ctx, name, metav1.GetOptions{})  // line 35
if errors.IsNotFound(err) {
    _, err = dyn.Resource(gvr).Namespace(namespace).Create(ctx, obj, metav1.CreateOptions{}) // line 40
} else {
    obj.SetResourceVersion(existing.GetResourceVersion())                                     // line 47
    _, err = dyn.Resource(gvr).Namespace(namespace).Update(ctx, obj, metav1.UpdateOptions{})  // line 48
}
```

This is the **create-or-update-with-full-overwrite** behaviour that makes adoption (M2 Task 2) hazardous: an `Update()` replaces the entire `.spec`.

#### Step 5 — Apply DAG-only manifests (lines 574–618)

```go
image, _ := options["image"].(string)
if image == "" { image = defaultAirflowImage }            // "quay.io/astronomer/ap-airflow"

imagePullSecret, ok := options["imagePullSecret"].(string)
if !ok {
    logger.Warn("ImagePullSecret not found in options, using default")
    image = defaultAirflowImage                            // BUG (lines 580-583)
}
```

> **The bug from `../03-gap-analysis.md` Gap 4 lives here**: the missing-imagePullSecret branch assigns to `image`, not `imagePullSecret`. Result: when `imagePullSecret` is absent, it stays empty and CronJob pulls can fail.

If `dagDeploymentType == utils.DagDeployTypeDagOnly`:

```go
manifests, err := utils.ParseJSON(request.K8SManifests)   // line 587-592
err = k.kube.ApplyK8sManifests(request.Namespace, manifests)  // line 596
```

Otherwise prior DAG-server manifests are deleted (lines 608–617).

#### Step 6 — Cleanup CronJob (line 620)

```go
k.kube.CronJob.CreateOrUpdateCleanupCronJob(request.Name, request.Namespace, image, imagePullSecret)
```

See [`commander/kubernetes/cronjob.go`](../../../../commander/kubernetes/cronjob.go):

- **`CreateOrUpdateCleanupCronJob()`** (lines 18–21) — deletes any existing cleanup CronJob by release label, then re-creates.
- **`CreateCleanupCronJob()`** (lines 52–103) — schedules `airflow-cleanup-pods` to run.
  - **Schedule** is computed by `calculateCleanupSchedule()` (lines 105–112) as `"%d-%d/%d * * * *"`:
    - start minute = `adler32(namespace) % InitialMinuteRange` (default 10),
    - interval = `CleanupIntervalInMinutes` (default 10),
    - upper bound = `FutureRunIntervals` (default 59).
    - Example: hash → 3 ⇒ `"3-59/10 * * * *"` (3:00, 3:10, 3:20, …, 3:50 every hour).
  - ServiceAccount: `{releaseName}-worker-serviceaccount` (line 58).
  - Container image: supplied Airflow image (line 84), command `airflow-cleanup-pods` (line 85), namespace arg (line 86).
  - Labels: `tier=airflow`, `release={releaseName}`, `component=airflow-cleanup-pods`.
  - `restartPolicy: OnFailure`.

#### Step 7 — Success response (line 622)

```go
return BuildResult(true, "Custom Resource Applied Successfully"), nil
```

This is the exact string Houston's worker matches against `COMMANDER_CUSTOM_RESOURCE_APPLIED` at line 43 of `houston-api/src/workers/deployment-upserted-for-create/index.js`.

### Provisioner — `DeleteCustomResource`

[`commander/provisioner/kubernetes/kubernetes.go:626-657`](../../../../commander/provisioner/kubernetes/kubernetes.go#L626-L657):

1. **Delete the CR** (line ~635) — `k.kube.Resource.DeleteCustomResource()` → dynamic-client `Delete()` at [`commander/kubernetes/custom_resource.go:57`](../../../../commander/kubernetes/custom_resource.go#L57).
2. **Delete cleanup CronJobs** (lines 641–644) — `k.kube.CronJob.DeleteByRelease(name, namespace)`.
3. **Delete the namespace** (lines 648–652) — `k.kube.Namespace.Delete()` with foreground propagation, zero grace period.
4. Returns `BuildResult(true, "Custom Resource Deleted Successfully")` (line 655).

### Logging

Representative lines (logrus):

| Event | File:line | Format |
|---|---|---|
| Apply entry | `kubernetes.go:493` | `Creating custom airflow definition with name  %s in namespace %s` |
| Namespace create error | `kubernetes.go:502` | `Error creating namespace: %s` |
| Platform secret sync error | `kubernetes.go:511` | `Error synchronizing secrets to new Airflow deployment namespace: %v` |
| CRD apply error | `kubernetes.go:569` | `Error inside ApplyCustomResource: %s` |
| Delete entry | `kubernetes.go:631` | `Deleting custom airflow definition with name  %s in namespace %s` |

Structured logger fields include `function` and `correlationId` (propagated from the gRPC request).

### Commander config

[`commander/config/config.go:21-35`](../../../../commander/config/config.go#L21-L35) — full struct:

| Field | Env var | Default | Purpose |
|---|---|---|---|
| `DebugMode` | `COMMANDER_DEBUG_MODE` | `true` | Logging verbosity |
| `HTTPPort` | `COMMANDER_HTTP_PORT` | `"8880"` | HTTP health check |
| `GRPCPort` | `COMMANDER_GRPC_PORT` | `"50051"` | gRPC service |
| `KubeConfig` | `COMMANDER_KUBECONFIG` | `""` | Empty = in-cluster |
| `HelmRepo` | `COMMANDER_HELM_REPO` | `"https://helm.astronomer.io"` | Helm repo URL |
| `HelmRepoName` | `COMMANDER_HELM_REPO_NAME` | `"astronomer-ee"` | Helm repo name |
| `PlatformRelease` | `COMMANDER_PLATFORM_RELEASE` | `""` | Platform release name |
| `PlatformNamespace` | `COMMANDER_PLATFORM_NAMESPACE` | `"astronomer"` | Source namespace for secret sync |
| `UpgradeTimeout` | `COMMANDER_UPGRADE_TIMEOUT` | `300` | Helm upgrade timeout (s) |
| `ManageNamespaceResource` | `COMMANDER_MANAGE_NAMESPACE_RESOURCE` | `true` | Gates namespace label/annotation management — **the existing 0.37 knob closest to "observe-only" mode** |
| `CleanupIntervalInMinutes` | `COMMANDER_CLEANUP_INTERVAL_IN_MINUTES` | `10` | Cleanup CronJob interval |
| `FutureRunIntervals` | `COMMANDER_FUTURE_RUN_INTERVALS` | `59` | Upper bound for cron schedule |
| `InitialMinuteRange` | `COMMANDER_INITIAL_MINUTE_RANGE` | `10` | Stagger offset for cleanup |

### K8s client wiring

[`commander/kubernetes/client.go:33-76`](../../../../commander/kubernetes/client.go#L33-L76):

- `New()` builds a composite `Client` from:
  - Structured `kube.Interface` via `kube.NewForConfig()` (line 37).
  - Dynamic client via `dynamic.NewForConfig()` (line 42).
- Sub-clients on the resulting struct: `Namespace`, `Secret`, `ConfigMap`, `PersistentVolumeClaim`, `Deployment`, `Resource` (dynamic-backed), `CronJob`, `Job`.
- Kubeconfig source: `KubeConfig` env var if set, else in-cluster ServiceAccount.

### Helm vs operator paths in commander

Both modes live in the same `KubeProvisioner` in 0.37, branched by RPC:

| Mode | RPCs | Provisioner methods | Helm client used? |
|---|---|---|---|
| Helm | `createDeployment`, `updateDeployment`, `upgradeDeployment`, `deleteDeployment` | `InstallDeployment` (100–179), `UpdateDeployment` (182–227), `UpgradeDeployment` (229–249), `DeleteDeployment` (251–304) | Yes — `helm/client.go` wrapping `helm.sh/helm/v3` |
| Operator | `ApplyCustomResource`, `DeleteCustomResource` | `ApplyCustomResource` (488–624), `DeleteCustomResource` (626–657) | No — dynamic K8s client |

The namespace-ensure and platform-secret-sync code paths are duplicated across both modes.

---

## How 0.37 maps onto the Operator Inheritance design docs

| Aspect in 0.37 | Affected by | Notes |
|---|---|---|
| Houston builds the full CR spec | [M3 / Task A](m3-task-a-spec-gen-to-commander.md) | We're moving this to Commander. The 1500-line `operator/index.js` is the artefact being relocated. |
| Commander's `ApplyCustomResource` does blind create-or-update | [M2 / Task 2](m2-task-2-connect-operator-to-commander.md) | The `Update()` overwrite path is what stomps adopted CRs. |
| `ManageNamespaceResource` flag exists | [M2 / Task 2](m2-task-2-connect-operator-to-commander.md), [M2 / Task 1](m2-task-1-install-dp.md) | Closest existing knob to "observe-only mode" — still creates resources, just doesn't add labels. |
| Platform secret sync logs and continues on failure | [`../03-gap-analysis.md`](../03-gap-analysis.md) Gap 5 → [Task C](m3-task-c-close-apc-gaps.md) | Silent failure pattern. |
| `imagePullSecret` assignment bug at `kubernetes.go:580-583` | [`../03-gap-analysis.md`](../03-gap-analysis.md) Gap 4 → [Task C](m3-task-c-close-apc-gaps.md) | Confirmed in 0.37. |
| MySQL probes read from `deployments.mode.operator.*.mysql.*` but unset in chart configmap | [`../03-gap-analysis.md`](../03-gap-analysis.md) Gap 1 / Gap 16 → [Task C](m3-task-c-close-apc-gaps.md) | Confirmed in 0.37. |
| `airflow.cfg` ConfigMap hardcodes K8s executor | _possible Gap_ — not formally captured | Operator-mode in 0.37 is K8s-executor in practice, regardless of `spec.executor`. |
| Cleanup CronJob runs `airflow-cleanup-pods` | M2 cleanup semantics | Adopted CRs may already have their own; collision with this CronJob's release label scheme needs handling. |
| `deployment-deleted` worker hard-deletes the row, then calls `DeleteCustomResource` which deletes the namespace | M2 / Task 2 delete semantics | Adopted CRs almost certainly should *not* have their namespace deleted on un-adopt. |
| DAG-server K8s manifests are templated by Houston via handlebars and shipped as raw YAML | [`../03-gap-analysis.md`](../03-gap-analysis.md) Gap 10 / Gap 11 → [Task A](m3-task-a-spec-gen-to-commander.md), [Task D](m3-task-d-close-operator-gaps.md) | The `k8sManifests` field is the carrier; long-term we may want a native DAG-server component on the CRD. |
| No Airflow 3.x / `apiServer` branch in `addAirflowComponentsToSpec()` | [`../03-gap-analysis.md`](../03-gap-analysis.md) Gap 2 → [Task A](m3-task-a-spec-gen-to-commander.md), [Task D](m3-task-d-close-operator-gaps.md) | Confirmed in 0.37 — only `webserver` is emitted. |

---

## Quick index

- Houston operator orchestrator → [`houston-api/src/lib/deployments/operator/index.js`](../../../../houston-api/src/lib/deployments/operator/index.js)
- Houston constants → [`houston-api/src/lib/constants/index.js`](../../../../houston-api/src/lib/constants/index.js)
- Houston workers → [`houston-api/src/workers/deployment-*`](../../../../houston-api/src/workers/)
- Commander proto → [`commander/_proto/custom_resource.proto`](../../../../commander/_proto/custom_resource.proto), [`commander/_proto/commander.proto`](../../../../commander/_proto/commander.proto)
- Commander handler → [`commander/api/custom_resource.go`](../../../../commander/api/custom_resource.go)
- Commander provisioner → [`commander/provisioner/kubernetes/kubernetes.go`](../../../../commander/provisioner/kubernetes/kubernetes.go)
- Commander k8s helpers → [`commander/kubernetes/custom_resource.go`](../../../../commander/kubernetes/custom_resource.go), [`commander/kubernetes/namespace.go`](../../../../commander/kubernetes/namespace.go), [`commander/kubernetes/secret.go`](../../../../commander/kubernetes/secret.go), [`commander/kubernetes/cronjob.go`](../../../../commander/kubernetes/cronjob.go), [`commander/kubernetes/client.go`](../../../../commander/kubernetes/client.go)
- Commander config → [`commander/config/config.go`](../../../../commander/config/config.go)
