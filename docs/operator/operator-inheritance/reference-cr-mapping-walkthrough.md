# Reference — Mapping a real 0.37 Airflow CR into Houston (worked example)

**Source data:** live cluster `k3d-astro037`, namespace `astronomer-electromagnetic-aphelion-3060`. Customer provided **only the cluster context and the namespace name** — everything below is recovered by working backwards from there.

**Purpose:** ground-truth mapping for [M2 / Task 3](m2-task-3-migrate-deployments-to-cp.md). This doc is the worked counterpart to the generic CR → Houston field table in that doc. It corrects several assumptions made there.

---

## Step 1 — Discover the CR from the namespace alone

```sh
# list Airflow CRs in the namespace
kubectl --context k3d-astro037 -n astronomer-electromagnetic-aphelion-3060 \
    get airflows.airflow.apache.org -o name

# -> airflow.airflow.apache.org/electromagnetic-aphelion-3060
```

The CR `name` is the **release name** without the `astronomer-` prefix:

- `metadata.name` = `electromagnetic-aphelion-3060` → `Deployment.releaseName`
- `metadata.namespace` = `astronomer-electromagnetic-aphelion-3060` → `Deployment.namespace`

The `astronomer-` prefix is the **platform release name** (`helm.releaseName` in Houston config). It's not a Houston field — informational only.

## Step 2 — Recover the workspace from the namespace, not the CR

The CR itself **does not record workspaceId anywhere**. The namespace labels do:

```sh
kubectl --context k3d-astro037 get ns astronomer-electromagnetic-aphelion-3060 \
    -o jsonpath='{.metadata.labels}'
```

```json
{
  "kubernetes.io/metadata.name": "astronomer-electromagnetic-aphelion-3060",
  "platform": "astronomer",
  "platform-release": "astronomer",
  "revision": "2",
  "workspace": "cmpcqawyq020917jt789yw7fd"
}
```

Houston also stamps `workspace` and `release` onto every pod's `podTemplateSpec.metadata.labels` inside the CR (e.g. `spec.scheduler.podTemplateSpec.metadata.labels.workspace`).

| Source | Field | Value |
|---|---|---|
| `namespace.metadata.labels.workspace` | `Deployment.workspaceId` (FK) | `cmpcqawyq020917jt789yw7fd` |
| `namespace.metadata.labels.platform-release` | `Deployment.config.adoption.platformRelease` | `astronomer` |
| `namespace.metadata.labels.revision` | `Deployment.revision` (Int) | `2` |
| `spec.<component>.podTemplateSpec.metadata.labels.workspace` | cross-check | should match the namespace label |

**Important:** if Houston's DB already has a workspace with that ID (because this CR came from the same CP being re-adopted, or from a CP backup), auto-rebind. If not, the operator picks/creates a workspace at adoption time.

## Step 3 — Identity and runtime

```jsonc
{
  "spec": {
    "image":          "quay.io/astronomer/astro-runtime:13.7.0",
    "runtimeVersion": "13.7.0",
    "executor":       "CeleryExecutor",
    "imagePullSecret": "electromagnetic-aphelion-3060-registry",
    "inClusterPostgres": false,
    "gid": 50000,
    "uid": 50000,
    "antiAffinity": "none",
    "databaseSSLMode": "disable",
    "useDefaultWorker": false,
    "useExternallyManagedFernetKey": false,
    "logRetentionDays": 15
  }
}
```

| CR field | Houston field | Notes |
|---|---|---|
| `spec.image` | `image` (upsert arg) | Customer registry preserved — `quay.io/astronomer/astro-runtime:13.7.0` here, but could be a private mirror. |
| `spec.runtimeVersion` | `Deployment.runtimeVersion` | `13.7.0` |
| Runtime → AF version map | `Deployment.runtimeAirflowVersion` | Runtime 13 = **Airflow 3.x class**, but see Step 4 caveat. |
| `spec.executor` | `executor` (upsert arg) | `CeleryExecutor` |
| `spec.imagePullSecret` | _(not mapped)_ | Already in-namespace as `<release>-registry`. Commander shouldn't recreate. |
| `spec.uid`, `spec.gid` | `Deployment.config.security.{uid,gid}` | Both 50000. |
| `spec.antiAffinity` | `Deployment.config.antiAffinity` | `"none"` |
| `spec.databaseSSLMode`, `spec.databaseSSLSecretName` | `Deployment.config.database.ssl.*` | `"disable"`, `""` |
| `spec.inClusterPostgres` | `Deployment.config.database.inCluster` | `false` |
| `spec.useExternallyManagedFernetKey` | `Deployment.config.fernet.externallyManaged` | `false` |
| `spec.logRetentionDays` | `Deployment.config.logging.retentionDays` | `15` |
| `metadata.annotations["astronomer.io/eligible-for-scaling"]` / `["astronomer.io/enable-scaling"]` | `Deployment.config.scaling.{eligible,enabled}` | both `false` |

## Step 4 — Airflow 3.x runtime, but `spec.webserver` (not `spec.apiServer`)

Runtime `13.7.0` is Airflow 3.x — yet the CR contains `spec.webserver`, **no `spec.apiServer`** block. This isn't a misconfiguration; it's [`03-gap-analysis.md` Gap 2](../03-gap-analysis.md#gap-2-airflow-3x-support-in-crd-generation-gap-2) in the wild: 0.37's Houston spec generator never emitted `apiServer` regardless of runtime version. The astro-runtime image carries enough Airflow 2 compat to make this work.

Implication for adoption:
- Keep the `webserver` block as-is.
- Mark `Deployment.config.adoption.specQuirks.airflow3xUsingWebserver = true` so we know to upgrade the spec when the customer eventually moves to a newer chart.
- Do **not** auto-introduce `spec.apiServer` during adoption — that's a separate planned upgrade (M3 Task A + D).

## Step 5 — Components

Component replicas + resources, exactly as found:

| Component | Present? | Replicas | CPU req/lim | Mem req/lim | Notable |
|---|---|---|---|---|---|
| `spec.scheduler` | ✅ | 1 | 500m / 500m | 1920Mi / 1920Mi | + sidecar `scheduler-gc` 100m/384Mi |
| `spec.workers[0]` (queue `default`) | ✅ | 1 | 1 / 1 | 3840Mi / 3840Mi | concurrency=16, KEDA disabled (`min=1,max=10`) |
| `spec.triggerer` | ✅ | 1 | 500m / 500m | 1920Mi / 1920Mi | + sidecar `triggerer-gc` |
| `spec.webserver` | ✅ | 1 | 500m / 500m | 1920Mi / 1920Mi | ingress block (see Step 7) |
| `spec.redis` | ✅ | 1 | 200m / 200m | 768Mi / 768Mi | |
| `spec.pgbouncer` | ✅ | 1 | 200m / 200m | 768Mi / 768Mi | `maxClientConn=165`, `metadataPoolSize=16`, `resultBackendPoolSize=5` |
| `spec.statsd` | ✅ | 1 | 200m / 200m | 768Mi / 768Mi | |
| `spec.dagProcessor` | present-but-**disabled** | — | — | — | `enabled: false` — scheduler does parsing inline |
| `spec.apiServer` | ❌ | — | — | — | See Step 4 |
| `spec.eventScheduler` | ❌ | — | — | — | AstroExecutor only |
| `spec.allocator` | ❌ | — | — | — | |
| DAGs server | ❌ | — | — | — | Image-baked DAGs in this deployment |

Houston mapping:

| CR path | Houston field |
|---|---|
| `spec.scheduler.replicas` / `.podTemplateSpec.spec.containers[name=scheduler].resources` | `scheduler` upsert arg |
| `spec.workers[i]` | `workers` upsert arg (first elem) + `Deployment.config.workers.extra[]` (elems 1..n) |
| `spec.workers[0].concurrency` | `workers.concurrency` |
| `spec.workers[0].queueName` | `workers.queueName` |
| `spec.workers[0].keda` | `workers.keda` |
| `spec.workers[0].isDefaultWorker` | `workers.isDefaultWorker` |
| `spec.triggerer.replicas` / resources | `triggerer` upsert arg |
| `spec.webserver.replicas` / resources | `webserver` upsert arg |
| `spec.pgbouncer.maxClientConn`, `metadataPoolSize`, `resultBackendPoolSize` | `pgbouncerConfig` |
| `spec.redis.*` | `Deployment.config.redis.*` (no first-class column) |
| `spec.statsd.*` | `Deployment.config.statsd.*` (no first-class column) |
| `spec.dagProcessor.enabled` | `Deployment.config.dagProcessor.enabled` |
| `spec.rbac.*` (allow*) | `Deployment.config.rbac.*` |

This particular CR has **only one worker group**; if the CR had multiple, the first goes into the `workers` upsert arg and extras spill into `Deployment.config.workers.extraGroups[]`.

## Step 6 — Customer env vars: not in the CR plaintext, in a Secret

The CR's per-component `env[]` arrays look like this:

```json
{
  "name": "TEST",
  "valueFrom": { "secretKeyRef": { "name": "electromagnetic-aphelion-3060-env", "key": "TEST" } }
},
{
  "name": "AIRFLOW__KUBERNETES_SECRETS__TEST",
  "valueFrom": { "secretKeyRef": { "name": "electromagnetic-aphelion-3060-env", "key": "AIRFLOW__KUBERNETES_SECRETS__TEST" } }
}
```

**Implication:** the actual customer-set env var *values* live in `Secret/<releaseName>-env`. To populate `Deployment.environmentVariables` correctly, the adoption flow must:

1. Read the CR's `env[]` from any one component (they're duplicated across all components).
2. Partition entries into:
   - **Platform-derived** (`AIRFLOW__ASTRONOMER__HOUSTON_JWK_URL`, `EXECUTOR_TYPE`, `SCARF_NO_ANALYTICS`, `DO_NOT_TRACK`, `ASTRONOMER_ENVIRONMENT`, `AIRFLOW__WEBSERVER__UPDATE_FAB_PERMS`, `AIRFLOW__SCHEDULER__STANDALONE_DAG_PROCESSOR`, `AIRFLOW__CORE__PARALLELISM`, `AIRFLOW__CELERY__WORKER_CONCURRENCY`, `AIRFLOW__SCHEDULER__PARSING_PROCESSES`, `AIRFLOW__TRIGGERER__DEFAULT_CAPACITY`, `AIRFLOW__WEBSERVER__WORKERS`, `AIRFLOW__ELASTICSEARCH__HOST*`) — these are auto-generated by Houston spec gen. **Do not import.** Houston will re-emit them.
   - **Customer-set** — anything with `valueFrom.secretKeyRef.name === "<releaseName>-env"`. **Import.**
3. For each customer-set entry, read `Secret/<releaseName>-env` and pull the value at the referenced key.
4. Stuff `{ name, value, isSecret: true }` into `Deployment.environmentVariables`.

For this CR the imported set is just:
- `TEST` (value from `<release>-env`)
- `AIRFLOW__KUBERNETES_SECRETS__TEST` (value from `<release>-env`)

The platform env vars number ~14 and would conflict on re-emission if imported.

## Step 7 — The webserver URL (path-based, not subdomain)

The `spec.webserver.ingress` block:

```json
{
  "host": "deployments.localtest.me",
  "path": "/electromagnetic-aphelion-3060/airflow",
  "tlsSecretName": "astronomer-tls",
  "annotations": {
    "nginx.ingress.kubernetes.io/auth-signin": "https://app.localtest.me/login",
    "nginx.ingress.kubernetes.io/auth-url":    "https://houston.localtest.me/v1/authorization",
    "kubernetes.io/ingress.class":             "astronomer-nginx",
    "nginx.ingress.kubernetes.io/configuration-snippet": "if ($host = 'astronomer-airflow.localtest.me' ) { return 308 https://deployments.localtest.me/electromagnetic-aphelion-3060/airflow/$request_uri; }"
  }
}
```

> **This corrects an assumption in the previous design docs.** Earlier the URL handling section assumed `<releaseName>-airflow.<baseDomain>` (subdomain pattern). The real 0.37 URL is **path-based**: `https://<deployments-subdomain>.<baseDomain>/<releaseName>/airflow`. The 308-redirect snippet is a legacy compat for old subdomain URLs.

Mapping:

| Source | Stored as |
|---|---|
| `spec.webserver.ingress.host` + `.path` | `Deployment.config.adoption.urls.webserver = "https://deployments.localtest.me/electromagnetic-aphelion-3060/airflow"` |
| `spec.webserver.ingress.tlsSecretName` | `Deployment.config.adoption.urls.tlsSecretName = "astronomer-tls"` |

Auth wiring (`auth-signin`, `auth-url`) tells us where the original CP lives — useful as a sanity-check at adoption time that the new CP's baseDomain matches (cookie-scope issue from earlier docs).

For [Task 1 § Deployment URL handling](m2-task-1-install-dp.md#deployment-url-handling--adopted-crs), this deployment falls into **Option B territory**: the existing URL is already under `localtest.me` (which is the CP baseDomain), so we can preserve `https://deployments.localtest.me/electromagnetic-aphelion-3060/airflow` directly and the JWT cookie scope works.

## Step 8 — Secrets and ConfigMaps in the namespace

```
secrets/                                                  configmaps/
  astronomer-houston-jwt-signing-certificate                <release>-airflow-config
  <release>-elasticsearch                                   <release>-local-settings-config
  <release>-env             (customer env var values)       <release>-webserver-config
  <release>-fernet-key
  <release>-metadata        (metadata DB URI)
  <release>-pgbouncer-config
  <release>-pgbouncer-connection
  <release>-pgbouncer-stats
  <release>-redis-connection
  <release>-redis-password
  <release>-registry        (dockerconfigjson)
  <release>-result-backend
  <release>-webserver-secret-key
```

`spec.secrets.*` references (also duplicated under each component's `airflowSecrets.*`):

| `spec.secrets.*` key | Secret in namespace | Houston field |
|---|---|---|
| `metadataSecretName` | `<release>-metadata` | `metadataConnectionJson` (read from secret on adopt) |
| `resultBackendSecretName` | `<release>-result-backend` | `resultBackendConnectionJson` |
| `fernetKeySecretName` | `<release>-fernet-key` | _(referenced, not stored in Houston)_ |
| `pgbouncerConnectionSecretName` | `<release>-pgbouncer-connection` | _(derived)_ |
| `redisConnectionSecretName` / `redisPasswordSecretName` | `<release>-redis-{connection,password}` | _(derived)_ |
| `webserverSecretKeySecretName` | `<release>-webserver-secret-key` | _(derived)_ |

The `astronomer-houston-jwt-signing-certificate` Secret was synced into the namespace by Commander at install (see [`reference-0.37-operator-mode.md`](reference-0.37-operator-mode.md) § Commander side, Step 2). For adoption: **do not re-sync** — it's already there.

ConfigMaps:

| ConfigMap | Content | Houston handling |
|---|---|---|
| `<release>-airflow-config` | `airflow.cfg` (INI) | Houston re-emits on next apply. **Don't import.** |
| `<release>-webserver-config` | `webserver_config.py` | Same — re-emit. |
| `<release>-local-settings-config` | `airflow_local_settings.py` | Same — re-emit. If the customer customized it, that's `Deployment.config.localSettings.custom = <content>` and we re-emit with their content. For this CR `customPodMutationHook: ""` and `extra: ""` — nothing custom. |

## Step 9 — Adoption-only metadata

Stuff to stash under `Deployment.config.adoption` so we never lose it:

```json
{
  "adoption": {
    "adopted": true,
    "adoptedAt": "<adoption timestamp>",
    "source": "operator-cr",
    "platformRelease": "astronomer",
    "originalCookieDomain": "localtest.me",
    "originalAuthUrls": {
      "signIn": "https://app.localtest.me/login",
      "authUrl": "https://houston.localtest.me/v1/authorization"
    },
    "urls": {
      "webserver": "https://deployments.localtest.me/electromagnetic-aphelion-3060/airflow",
      "tlsSecretName": "astronomer-tls"
    },
    "specQuirks": {
      "airflow3xUsingWebserver": true,
      "dagProcessorPresentButDisabled": true
    },
    "rawCRSnapshot": {
      "metadata": { "annotations": {...}, "labels": {...} },
      "spec": { /* full .spec verbatim */ }
    }
  }
}
```

## Final mapping table — this CR → `upsertDeployment` input

What an `adoptDeployment` mutation call would build for this CR:

```graphql
mutation {
  adoptDeployment(
    workspaceUuid: "cmpcqawyq020917jt789yw7fd"            # from namespace label
    clusterId:     "<dp-cluster-id>"                       # from current CP context (Task 1 registerCluster)
    crNamespace:   "astronomer-electromagnetic-aphelion-3060"
    crName:        "electromagnetic-aphelion-3060"
    label:         "electromagnetic-aphelion-3060"         # default to crName
  ) { id releaseName mode config }
}
```

> Arguments are flat top-level fields. The resolver fetches the full `.spec` itself via Commander `GetCustomResource` — the caller supplies only CR identity, not the spec.

Resolver-side, this becomes the upsert payload:

| `upsertDeployment` arg | Value derived from CR + namespace |
|---|---|
| `releaseName` | `electromagnetic-aphelion-3060` |
| `namespace` | `astronomer-electromagnetic-aphelion-3060` |
| `workspaceUuid` | `cmpcqawyq020917jt789yw7fd` |
| `clusterId` | (current DP cluster ID — Task 1) |
| `mode` | `"operator"` |
| `executor` | `"CeleryExecutor"` |
| `image` | `quay.io/astronomer/astro-runtime:13.7.0` |
| `runtimeVersion` | `13.7.0` |
| `scheduler` | `{ replicas: 1, resources: {cpu: "500m"/"500m", memory: "1920Mi"/"1920Mi", "ephemeral-storage": "1Gi"/"2Gi"} }` |
| `workers` | `{ replicas: 1, concurrency: 16, queueName: "default", keda: {enabled:false,min:1,max:10}, resources: {cpu:"1"/"1", memory:"3840Mi"/"3840Mi", "ephemeral-storage":"1Gi"/"2Gi"} }` |
| `triggerer` | `{ replicas: 1, resources: {cpu:"500m"/"500m", memory:"1920Mi"/"1920Mi"} }` |
| `webserver` | `{ replicas: 1, resources: {cpu:"500m"/"500m", memory:"1920Mi"/"1920Mi", "ephemeral-storage":"1Gi"/"2Gi"} }` |
| `apiServer` | _(omitted — none in CR, see Step 4)_ |
| `pgbouncerConfig` | `{ maxClientConn: 165, metadataPoolSize: 16, resultBackendPoolSize: 5 }` |
| `dagDeployment` | `{ type: "image" }` (image-baked; no DAG server present) |
| `environmentVariables` | `[ {name: "TEST", value: <from Secret>, isSecret: true}, {name: "AIRFLOW__KUBERNETES_SECRETS__TEST", value: <from Secret>, isSecret: true} ]` |
| `revision` | `2` (from namespace label) |
| `properties` / `config` | `{ adoption: {...}, redis: {...}, statsd: {...}, dagProcessor: {enabled:false}, rbac: {...}, security: {uid:50000,gid:50000}, antiAffinity:"none", logging:{retentionDays:15}, database:{ssl:{mode:"disable",secretName:""}, inCluster:false}, fernet:{externallyManaged:false}, scaling:{eligible:false,enabled:false} }` |

## CRD extension surface — what's first-class vs what isn't

The Astro Runtime Operator CRD intentionally keeps its first-class surface narrow. Most extensions land in either `spec.env` / `spec.envFrom` (passed to Airflow as native config) or the per-component `podTemplateSpec` (sidecars, volumes, custom containers). This matters for adoption because most "customer-flavoured" content in a CR sits in those generic hooks, not in dedicated CRD fields.

### Logs

| Extension | Native CRD field? | Where |
|---|---|---|
| Log retention | ✅ `int` | `spec.logRetentionDays` (default 15). Just GC retention, not shipping. |
| KubernetesExecutor task-log PVC | ✅ `*corev1.PersistentVolumeClaimSpec` | `spec.logs.persistentVolumeClaimSpec`. Creates a PVC mounted to webserver + KExec task pods for task-log reads. Only relevant if remote logging isn't configured. |
| Per-component log serving port | ✅ | `spec.<component>.logServingPort` (default 8793) |
| ElasticSearch / S3 / GCS / Loki / Datadog logs | ❌ no field | Configured via `AIRFLOW__LOGGING__REMOTE_*` and `AIRFLOW__ELASTICSEARCH__*` env vars on `spec.env` / `envFrom`. Confirmed by this CR: ES is wired via two env vars sourced from `Secret/<release>-elasticsearch`. |
| Custom log shipper sidecar (Fluentd / Fluent-bit / Vector) | ❌ | Add via `spec.<component>.podTemplateSpec`. |

The operator delegates log-shipping entirely to (a) Airflow's env-driven config, or (b) platform-level shippers (in APC 0.37, Vector runs as a platform DaemonSet from `charts/vector/`, not under the operator).

### Metrics

| Extension | Native CRD field? | Where |
|---|---|---|
| StatsD enable / replicas / resources / hostname / ports | ✅ `*StatsdSpec` | `spec.statsd.{enabled, replicas, resources, hostName, ingestPort, scrapePort, image, customLabels, enableNetworkPolicies, nodeSelector, tolerations}` |
| StatsD pod customisation (sidecars, env, args) | ✅ `*common.PodTemplateSpec` | `spec.statsd.podTemplateSpec`. The CRD comment says *"Custom metrics forwarding, e.g. forwarding to a Datadog backend can be configured here"* — meaning **via a sidecar**, not a `datadog: {…}` block. |
| StatsD mappings.yml | ❌ no field | Default baked into the operator image (`--statsd.mapping-config=/etc/statsd-exporter/mappings.yml`). Override via `spec.statsd.podTemplateSpec`. |
| Prometheus scrape | ❌ | Configured at the platform Prometheus level (`astronomer/charts/prometheus/templates/prometheus-config-configmap.yaml`). |
| Datadog / OpenTelemetry / Prometheus remote_write | ❌ | Sidecar in `spec.statsd.podTemplateSpec`. |

### Airflow DB (metadata + result backend)

| Extension | Native CRD field? | Where |
|---|---|---|
| Customer-supplied metadata DB Secret | ✅ | `spec.secrets.metadataSecretName` (key `connection`) |
| Customer-supplied result backend Secret | ✅ | `spec.secrets.resultBackendSecretName` |
| Externally managed Fernet key | ✅ `*bool` | `spec.useExternallyManagedFernetKey` + `spec.secrets.fernetKeySecretName` |
| Embedded in-cluster Postgres (dev only) | ✅ `*bool` | `spec.inClusterPostgres` (default `false`); when `true`, `spec.postgres.*` is the embedded postgres config |
| SSL mode (component → pgbouncer/DB) | ✅ enum | `spec.databaseSSLMode` ∈ `disable / allow / prefer / require / verify-ca / verify-full` |
| SSL CA secret | ✅ | `spec.databaseSSLSecretName` |
| pgbouncer config | ✅ `*PgBouncerSpec` | `spec.pgbouncer.*` — `maxClientConn`, `metadataPoolSize`, `resultBackendPoolSize`, `clientSSLMode`, images, resources |
| **MySQL backend** | ❌ no first-class field | Works only via the metadata Secret content + Airflow env vars; **pgbouncer is bypassed** for MySQL. This is the root of [`../03-gap-analysis.md`](../03-gap-analysis.md) Gap 1 / Gap 16. |
| External secret manager (AWS Secrets, Vault) | ❌ | `AIRFLOW__SECRETS__BACKEND*` env vars |
| External Redis | ❌ | No "use my Redis" toggle |

### The big general-purpose extension hooks

These are what an adopted CR is most likely to carry customer-specific content in. Anything below MUST be preserved during adoption — server-side apply should claim only structural fields and never these.

| Hook | Field | What you'd find in it |
|---|---|---|
| Per-component pod customisation | `spec.<component>.podTemplateSpec` (`common.PodTemplateSpec` wraps `corev1.PodTemplateSpec` with `+kubebuilder:pruning:PreserveUnknownFields`) | Sidecars (log shippers, metric forwarders, dogstatsd), init containers, custom volumes / volumeMounts, security contexts, tolerations, affinity, IRSA / Workload Identity annotations. **The single most important extension hook.** |
| Global env + envFrom | `spec.env`, `spec.envFrom` | Customer-set Airflow config, secret backend wiring, ES connection, remote logging URLs |
| Per-component env override | `spec.<component>.env`, `spec.<component>.envFrom` | Component-specific overrides |
| Airflow plugins | `spec.airflowPlugins[]` (`name, image, sourcePath, destinationPath, pythonPath, airflowComponents[]`) | Init containers that copy plugins from a plugin image into airflow components and update PYTHONPATH |
| Custom KubernetesExecutor pod template | `spec.podTemplateConfigMapName` | Customer-supplied configmap with key `pod_template_file.yaml` — **fully replaces** the operator's default. Customers using KExec heavily often customise this. |
| Custom pod mutation logic | `spec.localSettings.customPodMutationHook` + `spec.localSettings.extra` | Python injected into `airflow_local_settings.py` |
| Cloud IAM | `spec.serviceAccountAnnotations` | IRSA / Workload Identity annotations applied to all component SAs |
| Non-worker scheduling | `spec.systemNodeSelector`, `spec.systemTolerations` | Place non-worker pods on dedicated nodes |
| Task data PVC | `spec.dataVolume.persistentVolumeClaimSpec` | Shared volume across workers / triggerers / KExec tasks |
| Extra NetworkPolicy ingress | `spec.<component>.extraNetworkPolicyRules.ingress[]` | Additional ingress rules layered on top of the operator's defaults |
| AstroExecutor mode | `spec.executionModes[]` | `["hosted"]` / `["remote"]` / both (Laminar) |

### Implications for adoption (M2 / Task 2 + 3)

1. **Field-ownership matrix narrows.** Server-side apply with field manager `apc-commander` should claim **only** structural fields (replicas, image, runtimeVersion, executor, resources, replica-count, secret references that APC owns). It must **never** claim:
   - any `podTemplateSpec`
   - `env` / `envFrom` (any component)
   - `airflowPlugins`
   - `podTemplateConfigMapName`
   - `localSettings.customPodMutationHook` / `localSettings.extra`
   - `serviceAccountAnnotations`
   - `systemNodeSelector` / `systemTolerations`
   - `dataVolume`, `logs`
   - `extraNetworkPolicyRules`

2. **No Houston column for most extension content.** `Deployment.config.adoption.rawCRSnapshot` is the only durable home for `airflowPlugins`, `podTemplateConfigMapName` content, customer SA annotations, customer env vars beyond the simple ones, etc. APC stays **strictly read-only** on them.

3. **MySQL needs Secret-content sniffing.** No CR field tells us "this is MySQL". The catalogue mapper has to read `Secret/<release>-metadata` and parse the connection string to detect MySQL — and then flag the deployment with `Deployment.config.adoption.specQuirks.databaseType = "mysql"`.

4. **Customer log/metric backends are env-driven, not CRD-driven.** A customer with their own ES has the connection string in `Secret/<release>-elasticsearch` and env vars on each component. Adoption preserves these as-is; if the customer later wants to rewire to APC's ES, that's a *separate* day-2 reconciliation.

---

## Updates to the generic table in `m2-task-3-migrate-deployments-to-cp.md`

This worked example surfaces a handful of corrections to the generic mapping I wrote earlier in [`m2-task-3-migrate-deployments-to-cp.md` § Phase A](m2-task-3-migrate-deployments-to-cp.md#phase-a--catalogue-an-existing-airflow-cr):

| Original assumption | Correction |
|---|---|
| "Customer env vars come from `spec.airflow.config.env`" | **Wrong.** They live in `Secret/<releaseName>-env` and are referenced via `secretKeyRef` from each component's `env[]`. Adoption must read both the CR and the env Secret. |
| "Workspace assignment is open — collect at adoption time" | **Partially wrong.** Workspace ID is recorded on the namespace label `workspace=` and on every pod template label. Auto-recover; only ask the operator if the label is missing. |
| "Webserver URL = `<releaseName>-airflow.<baseDomain>` (subdomain)" | **Wrong for 0.37.** Real pattern is path-based: `<deployments-subdomain>.<baseDomain>/<releaseName>/airflow`. Adoption stores whatever ingress host+path are on the CR. |
| "AF 3.x CR has `apiServer`" | **Not in 0.37.** Even for runtime 13 (AF 3.x class), 0.37 emits `webserver`, not `apiServer`. Adoption must accept this and flag it as a spec quirk. |
| "Redis / Statsd / DAG processor have no first-class Houston fields → stash in `config` JSON" | **Confirmed.** No change. |
| "`spec.dagDeployment` maps to `dagDeployment` arg" | Reality is more nuanced — 0.37 image-baked deployments have **no** `spec.dagDeployment` block at all. DAG-server deployments would. |
| "RBAC migration is mostly out-of-band" | Confirmed — no user data in the CR. Namespace labels confirm the workspace but not which users have access. |

A follow-up edit to `m2-task-3-migrate-deployments-to-cp.md` should incorporate these corrections.
