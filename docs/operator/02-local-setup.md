# Airflow Operator Local Development Setup

This document covers how to set up a local APC environment with the Airflow Operator enabled for development and testing.

---

## Prerequisites

| Tool | Required Version | Install |
|------|-----------------|---------|
| Docker | 20.10+ | [docker.com](https://docs.docker.com/get-docker/) |
| k3d | v5.x | `brew install k3d` |
| kubectl | 1.28+ | `brew install kubectl` |
| helm | 3.12+ | `brew install helm` |
| mkcert | latest | `brew install mkcert && mkcert -install` |

---

## Quick Start (Automated)

A setup script is provided at `bin/setup-operator-k3d.py`. It creates a single unified-plane k3d cluster with the Airflow Operator enabled.

```bash
# From the astronomer repo root:
python3 bin/setup-operator-k3d.py

# With custom domain:
python3 bin/setup-operator-k3d.py --base-domain local.astro.dev

# With MySQL instead of PostgreSQL for Airflow metadata DB:
python3 bin/setup-operator-k3d.py --airflow-db mysql

# Skip steps you've already done:
python3 bin/setup-operator-k3d.py --skip-certs --skip-clusters

# With extra Helm values:
python3 bin/setup-operator-k3d.py --helm-values /path/to/custom-values.yaml

# Recreate the cluster from scratch:
python3 bin/setup-operator-k3d.py --recreate-cluster
```

### What the Script Does

1. Validates prerequisites (docker, k3d, kubectl, helm, mkcert)
2. Sets up local pull-through registry proxies (quay.io, docker.io, etc.)
3. Generates TLS certificates with mkcert
4. Creates a k3d cluster (`operator-dev`)
5. Creates the `astronomer` namespace + TLS secrets
6. Generates Helm values with operator enabled:
   - `global.airflowOperator.enabled: true`
   - `airflow-operator.crd.create: true`
   - `airflow-operator.certManager.enabled: true`
7. Runs `helm upgrade --install` with the astronomer chart
8. Waits for operator pod readiness
9. Verifies CRDs are installed and webhooks are running
10. Prints `/etc/hosts` entries and next steps

---

## Manual Setup (Step by Step)

If you prefer to set up manually or need to debug individual steps:

### Step 1: Create k3d Cluster

```bash
k3d cluster create operator-dev \
  --no-lb \
  --k3s-arg "--disable=traefik@server:0" \
  -p "443:443@server:0" \
  -p "80:80@server:0" \
  --wait
```

### Step 2: Create Namespace and TLS Secrets

```bash
kubectl create namespace astronomer

# Generate TLS certs (adjust domain as needed)
mkcert -cert-file tls.crt -key-file tls.key \
  "localtest.me" "*.localtest.me"

# Append mkcert root CA to cert for full chain
cat "$(mkcert -CAROOT)/rootCA.pem" >> tls.crt

kubectl create secret tls astronomer-tls \
  --cert=tls.crt --key=tls.key \
  -n astronomer

kubectl create secret generic mkcert-root-ca \
  --from-file=ca.crt="$(mkcert -CAROOT)/rootCA.pem" \
  -n astronomer
```

### Step 3: Generate Helm Values

Create a file `operator-values.yaml`:

```yaml
global:
  plane:
    mode: unified

  baseDomain: localtest.me
  tlsSecret: astronomer-tls

  # Enable the Airflow Operator
  airflowOperator:
    enabled: true

  # Required for local dev
  postgresql:
    enabled: true

  # Reduce resource usage for local dev
  platformNodePool:
    nodeSelector: {}
    affinity: {}
    tolerations: []

# Operator subchart values
airflow-operator:
  crd:
    create: true
  certManager:
    enabled: true
  images:
    manager:
      repository: quay.io/astronomer/airflow-operator-controller
      tag: 1.5.2
  manager:
    replicas: 1
    resources:
      limits:
        cpu: 600m
        memory: 500Mi
      requests:
        cpu: 200m
        memory: 128Mi

# Minimize resource usage for local dev
astronomer:
  houston:
    replicas: 1
  astroUI:
    replicas: 1
  commander:
    replicas: 1
  registry:
    replicas: 1

nginx:
  replicas: 1

elasticsearch:
  client:
    replicas: 1
  master:
    replicas: 1
  data:
    replicas: 1

nats:
  replicas: 1
```

### Step 4: Install the Chart

```bash
# Update dependencies
helm dep update .

# Install
helm upgrade --install astronomer . \
  -n astronomer \
  -f operator-values.yaml \
  --timeout 60m \
  --wait
```

### Step 5: Verify Operator Installation

```bash
# Check operator pod is running
kubectl get pods -n astronomer -l app=airflow-operator-controller-manager

# Check CRDs are installed
kubectl get crds | grep airflow.apache.org

# Expected CRDs:
# airflows.airflow.apache.org
# apiservers.airflow.apache.org
# dagprocessors.airflow.apache.org
# pgbouncers.airflow.apache.org
# postgreses.airflow.apache.org
# rbacs.airflow.apache.org
# redises.airflow.apache.org
# schedulers.airflow.apache.org
# statsds.airflow.apache.org
# triggerers.airflow.apache.org
# webservers.airflow.apache.org
# workers.airflow.apache.org

# Check webhooks
kubectl get validatingwebhookconfigurations | grep airflow
kubectl get mutatingwebhookconfigurations | grep airflow

# Check operator logs
kubectl logs -n astronomer -l app=airflow-operator-controller-manager --tail=50
```

### Step 6: Add /etc/hosts Entries

```bash
# Get the nginx LoadBalancer IP (or use 127.0.0.1 for k3d port-forward)
sudo sh -c 'echo "127.0.0.1 localtest.me app.localtest.me houston.localtest.me grafana.localtest.me" >> /etc/hosts'
```

---

## Creating an Operator Deployment

### Via the UI

1. Navigate to `https://app.localtest.me`
2. Create a workspace (if none exists)
3. Click "New Deployment"
4. In the deployment form, select **Deployment Mode: Operator**
5. Choose executor (CeleryExecutor or KubernetesExecutor)
6. Complete the form and create

### Via GraphQL API

```graphql
mutation {
  upsertDeployment(
    workspaceUuid: "<workspace-uuid>"
    type: "airflow"
    label: "my-operator-deployment"
    mode: "operator"
    executor: "CeleryExecutor"
    airflowVersion: "2.10.4"
  ) {
    id
    releaseName
    mode
    status
  }
}
```

Send this to `https://houston.localtest.me/v1` with an authorization token.

### Via kubectl (Direct CRD)

For testing the operator directly without Houston/Commander:

```bash
kubectl apply -f - <<EOF
apiVersion: airflow.apache.org/v1beta1
kind: Airflow
metadata:
  name: test-airflow
  namespace: astronomer-test-ns
spec:
  executor: CeleryExecutor
  image: quay.io/astronomer/astro-runtime:12.5.0
  runtimeVersion: "12.5.0"
  scheduler:
    replicas: 1
  webserver:
    replicas: 1
  workers:
    - name: default
      replicas: 1
  redis:
    replicas: 1
  statsd:
    replicas: 1
EOF
```

---

## Inspecting Operator Deployments

```bash
# List all Airflow CRs across namespaces
kubectl get airflows -A

# Describe a specific Airflow CR
kubectl describe airflow <name> -n <namespace>

# Check component status
kubectl get airflow <name> -n <namespace> -o jsonpath='{.status.conditions}'

# Watch operator logs for a specific deployment
kubectl logs -n astronomer -l app=airflow-operator-controller-manager -f | grep <namespace>

# Check all pods in a deployment namespace
kubectl get pods -n <deployment-namespace>

# Check scheduler logs
kubectl logs -n <namespace> -l component=scheduler

# Check webserver logs
kubectl logs -n <namespace> -l component=webserver
```

---

## Testing Individual Components Locally

### Houston API (Local)

```bash
cd houston-api

# Install dependencies
npm install

# Run with operator mode enabled in config
# Set environment variable or use local config
export DEPLOYMENTS__MODE__OPERATOR__ENABLED=true

# Start Houston
npm run start:local
```

### Commander (Local)

```bash
cd commander

# Build
make build

# Run with kubeconfig pointing to k3d cluster
KUBECONFIG=$HOME/.kube/config ./commander
```

### Airflow Operator (Local, outside cluster)

```bash
cd airflow-operator

# Configure local webhook certs
make configure-local-webhook

# Run the operator against the k3d cluster
make run
```

### Airflow Operator (In-cluster, standalone KinD)

```bash
cd airflow-operator

# Start a KinD cluster with KEDA and cert-manager
make kind-start

# Build and deploy operator, run integration tests
make kind-test
```

---

## Troubleshooting

### Operator pod not starting

```bash
# Check events
kubectl get events -n astronomer --sort-by='.lastTimestamp' | grep operator

# Common causes:
# - cert-manager not ready (webhook cert not issued)
# - Image pull failure (check registry access)
# - RBAC issues (check ClusterRole/ClusterRoleBinding)
```

### CRDs not created

```bash
# Verify the chart was installed with crd.create=true
helm get values astronomer -n astronomer | grep -A5 airflow-operator

# If CRDs are missing, apply manually:
kubectl apply -f charts/airflow-operator/templates/crds/
```

### Webhook failures

```bash
# Check cert-manager certificate status
kubectl get certificates -n astronomer | grep airflow

# Check webhook configuration
kubectl get validatingwebhookconfigurations -o yaml | grep -A10 airflow

# If using custom TLS certs, verify they're in the right secret
kubectl get secret webhook-server-cert -n astronomer -o yaml
```

### Deployment creation fails (Houston/Commander)

```bash
# Check Houston logs
kubectl logs -n astronomer -l component=houston --tail=100 | grep operator

# Check Commander logs
kubectl logs -n astronomer -l component=commander --tail=100 | grep -i "custom\|resource\|apply"

# Check Houston worker logs (where CRD spec is generated)
kubectl logs -n astronomer -l component=houston-worker --tail=100 | grep operator
```

### Operator deployment stuck in "Creating"

```bash
# Check operator controller logs for reconciliation errors
kubectl logs -n astronomer -l app=airflow-operator-controller-manager --tail=200

# Check the Airflow CR status conditions
kubectl get airflow <name> -n <namespace> -o yaml | grep -A20 conditions

# Common causes:
# - Missing secrets (Fernet key, DB connection)
# - DB not reachable
# - Image pull errors in deployment namespace
```

### MySQL-specific issues

```bash
# If using MySQL backend, verify probe configs are present
# Houston needs deployments.mode.operator.{component}.mysql.{probe} config
# Check if these are set in Houston configmap:
kubectl get configmap astronomer-houston-config -n astronomer -o yaml | grep -A5 mysql
```
