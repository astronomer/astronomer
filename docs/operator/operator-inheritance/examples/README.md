# Standalone operator — production-ready CR

[`production-airflow.yaml`](production-airflow.yaml) is a heavily-commented `Airflow` CR for the **standalone Astro Runtime Operator** (no APC).
It exercises every extension hook documented in [`../reference-cr-mapping-walkthrough.md`](../reference-cr-mapping-walkthrough.md) § *CRD extension surface*.

Builds on the operator team's own integration-test fixtures:

- [`integration-tests/airflow_deployments/v1beta1/consolidated-airflow.yaml`](../../../../../airflow-operator/integration-tests/airflow_deployments/v1beta1/consolidated-airflow.yaml) — KEDA + sidecars + custom pod mutation + logs PVC
- [`integration-tests/airflow_deployments/v1beta1/consolidated-airflow-v3.yaml`](../../../../../airflow-operator/integration-tests/airflow_deployments/v1beta1/consolidated-airflow-v3.yaml) — same with `apiServer` (Airflow 3.x) + AstroAgent fields
- [`integration-tests/airflow_deployments/v1beta1/ha-airflow.yaml`](../../../../../airflow-operator/integration-tests/airflow_deployments/v1beta1/ha-airflow.yaml) — HA scheduler / pgbouncer
- [`integration-tests/airflow_deployments/v1beta1/sidecars.yaml`](../../../../../airflow-operator/integration-tests/airflow_deployments/v1beta1/sidecars.yaml) — statsd metrics-forwarder pattern

Plus the real 0.37 CR I previously walked through in [`../reference-cr-mapping-walkthrough.md`](../reference-cr-mapping-walkthrough.md) — for sensible resource defaults, pgbouncer pool sizes, env-var set.

---

## Prerequisites

The standalone operator brings none of the APC platform pieces, so everything has to be wired in by hand.

### 1. cert-manager (operator webhooks)

```sh
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.15.3/cert-manager.yaml
kubectl -n cert-manager wait --for=condition=Available --timeout=120s \
  deploy/cert-manager deploy/cert-manager-cainjector deploy/cert-manager-webhook
```

### 2. The operator itself

```sh
helm repo add astronomer https://helm.astronomer.io
helm upgrade --install airflow-operator-system astronomer/airflow-operator \
  -n airflow-operator-system --create-namespace
```

### 3. Optional but recommended add-ons

- **KEDA** (required for the worker autoscaling block):
  ```sh
  helm repo add kedacore https://kedacore.github.io/charts
  helm upgrade --install keda kedacore/keda -n keda --create-namespace
  ```
- **Prometheus** (to scrape the metrics that flow through statsd) — any flavour; the CR's NetworkPolicy assumes a Prometheus pod labeled `app.kubernetes.io/name=prometheus` in namespace `monitoring`.
- **External Postgres** + a Secret in the deployment namespace containing the connection URI.

### 4. Pre-create Secrets and ConfigMaps in the deployment namespace

Create the namespace first:

```sh
kubectl create namespace airflow-prod
```

Then the Secrets the CR references (replace values with real ones):

```sh
# --- Metadata DB ---
kubectl -n airflow-prod create secret generic prod-airflow-metadata \
  --from-literal=connection='postgresql+psycopg2://airflow_user:PWD@db.example.com:5432/airflow_meta?sslmode=verify-full'

# --- Result backend (Celery) ---
kubectl -n airflow-prod create secret generic prod-airflow-result-backend \
  --from-literal=connection='db+postgresql://airflow_user:PWD@db.example.com:5432/airflow_meta?sslmode=verify-full'

# --- Fernet key (32-byte base64) ---
kubectl -n airflow-prod create secret generic prod-airflow-fernet-key \
  --from-literal=fernet-key="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"

# --- Webserver session secret key ---
kubectl -n airflow-prod create secret generic prod-airflow-webserver-secret-key \
  --from-literal=webserver-secret-key="$(openssl rand -base64 32)"

# --- Redis connection / password ---
kubectl -n airflow-prod create secret generic prod-airflow-redis-password \
  --from-literal=password="$(openssl rand -base64 24)"
kubectl -n airflow-prod create secret generic prod-airflow-redis-connection \
  --from-literal=connection='redis://:PWD@prod-airflow-redis:6379/0'

# --- Pgbouncer connection (operator can also derive this) ---
kubectl -n airflow-prod create secret generic prod-airflow-pgbouncer-connection \
  --from-literal=connection='postgresql://airflow_user:PWD@prod-airflow-pgbouncer:6543/airflow_meta'

# --- DB TLS CA cert (only if databaseSSLMode=verify-* and you bring your own CA) ---
kubectl -n airflow-prod create secret generic prod-airflow-db-ca \
  --from-file=ca.crt=/path/to/db-ca.crt

# --- Elasticsearch (remote logging backend) ---
kubectl -n airflow-prod create secret generic prod-airflow-elasticsearch \
  --from-literal=connection='https://elastic:PWD@es.example.com:9243'

# --- Image pull secret ---
kubectl -n airflow-prod create secret docker-registry prod-airflow-registry \
  --docker-server=quay.io --docker-username=YOUR_USER --docker-password=YOUR_TOKEN \
  --docker-email=you@example.com
```

The CR also expects a ConfigMap holding the KubernetesExecutor task pod template:

```sh
kubectl -n airflow-prod create configmap prod-airflow-kexec-pod-template \
  --from-file=pod_template_file.yaml=/path/to/your/pod_template_file.yaml
```

A minimal `pod_template_file.yaml` is in the [Airflow docs](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/executor/kubernetes.html#pod-template-file).

### 5. Apply the CR

```sh
kubectl apply -f production-airflow.yaml
kubectl -n airflow-prod get airflow prod-airflow -w
# wait for status.conditions[*]={SchedulerReady, WebserverReady, TriggererReady} True
```

---

## What the CR exercises (one-line each)

| Capability | CR field |
|---|---|
| External Postgres + SSL | `spec.secrets.metadataSecretName` + `databaseSSLMode=verify-full` + `databaseSSLSecretName` |
| Externally managed Fernet | `useExternallyManagedFernetKey=true` + `secrets.fernetKeySecretName` |
| Remote logging — Elasticsearch | `spec.env` (`AIRFLOW__LOGGING__REMOTE_LOGGING`, `AIRFLOW__ELASTICSEARCH__HOST`) |
| Remote logging — S3 alternative | (commented in YAML; swap the AF env vars) |
| External secret manager (AWS) | `AIRFLOW__SECRETS__BACKEND` env |
| IRSA (EKS) | `serviceAccountAnnotations: eks.amazonaws.com/role-arn: ...` |
| Statsd → Prometheus scrape | `spec.statsd.extraNetworkPolicyRules.ingress` + statsd `podTemplateSpec` annotations |
| Statsd → Datadog forwarder sidecar | second container under `spec.statsd.podTemplateSpec` |
| HA scheduler | `spec.scheduler.replicas=2` + `spec.antiAffinity=zone` |
| HA pgbouncer | `spec.pgbouncer.replicas=2` |
| Multiple Celery queues | `spec.workers[]` with two entries |
| KEDA autoscaling | `spec.workers[*].keda` |
| KubernetesExecutor pod template | `spec.podTemplateConfigMapName` |
| Custom pod mutation hook | `spec.localSettings.customPodMutationHook` |
| Airflow plugin via init-container | `spec.airflowPlugins[]` |
| Shared task-data PVC | `spec.dataVolume.persistentVolumeClaimSpec` |
| KExec task-log PVC | `spec.logs.persistentVolumeClaimSpec` |
| Node placement for non-workers | `spec.systemNodeSelector` + `spec.systemTolerations` |
| Per-worker-queue node placement | `spec.workers[*].podTemplateSpec.spec.nodeSelector` |
| NetworkPolicy customisation | per-component `extraNetworkPolicyRules.ingress` |
| Pod annotations (scraper hints) | `spec.<component>.podAnnotations` |

---

## Customisation cheat sheet

| Want | Change |
|---|---|
| Airflow 3.x runtime | Replace `webserver` block with `apiServer`. Add `astroAgentVersion`. See `consolidated-airflow-v3.yaml`. |
| KubernetesExecutor instead of Celery | `executor: KubernetesExecutor`. Drop `redis` and `workers[]`. Keep `podTemplateConfigMapName`. |
| AstroExecutor / Laminar | `executor: AstroExecutor`, add `eventScheduler:` block, `executionModes: ["hosted", "remote"]`, populate `astroAgentVersion`, `astroAgentSystemImage`, `astroAgentClientImage`. |
| Skip the operator's NetworkPolicies | `enableNetworkPolicies: false` (top-level + per-component) |
| Run an embedded postgres (dev only — DO NOT use in prod) | `inClusterPostgres: true` + remove `secrets.metadataSecretName` / `resultBackendSecretName` |
| GKE Workload Identity instead of IRSA | Replace `serviceAccountAnnotations.eks.amazonaws.com/role-arn` with `iam.gke.io/gcp-service-account: ...` |
| OpenShift | Add `+kubebuilder:scc` annotation on the namespace, set `spec.statsd.enableNetworkPolicies=false` if SCC blocks net-policies, audit container `securityContext` |
| Remote logging via S3 instead of ES | Swap the `AIRFLOW__ELASTICSEARCH__*` env vars for `AIRFLOW__LOGGING__REMOTE_*` and drop the ES Secret |
| Different Datadog forwarding (cluster-level dogstatsd) | Drop the `datadog-forwarder` sidecar; instead point `AIRFLOW__METRICS__STATSD_HOST` directly to the Datadog DaemonSet's service |
| HA triggerer | `spec.triggerer.replicas: 2` |
| Disable triggerer entirely (e.g. no deferrable ops) | Note: this is currently broken per [`../03-gap-analysis.md` Gap 15](../../03-gap-analysis.md) |

---

## Field-level reference

For every field used above, the Go type definition is in:
- `airflow-operator/apis/airflow/v1beta1/airflow_types.go` — `AirflowSpec` (top-level)
- `airflow-operator/apis/airflow/v1beta1/<component>_types.go` — per-component specs
- `airflow-operator/apis/airflow/common/types.go` — `PodTemplateSpec`, `ExtraNetworkPolicyRules`, `PersistentVolumeClaimSpec`

The extension hooks and what's first-class vs not are catalogued in [`../reference-cr-mapping-walkthrough.md`](../reference-cr-mapping-walkthrough.md) § *CRD extension surface*.
