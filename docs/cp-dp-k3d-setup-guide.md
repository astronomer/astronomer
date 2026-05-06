# Astronomer CP/DP Setup Guide for k3d Clusters

This guide walks you through setting up Astronomer with a Control Plane (CP) and Data Plane (DP) architecture using two k3d clusters.

> **Why k3d over kind?** k3d uses Flannel CNI by default, which handles external routing better than Calico. Pods can reach external IPs (like other clusters on the Docker network) without the CIDR overlap issues found in kind + Calico setups.

## Architecture Overview

```
┌─────────────────────────────────────┐    ┌─────────────────────────────────────┐
│       Control Plane Cluster         │    │        Data Plane Cluster           │
│                                     │    │                                     │
│  ┌─────────────┐  ┌─────────────┐   │    │  ┌─────────────┐  ┌─────────────┐   │
│  │  Houston    │  │  Astro UI   │   │    │  │  Commander  │  │  Registry   │   │
│  │    API      │  │             │   │    │  │             │  │             │   │
│  └─────────────┘  └─────────────┘   │    │  └─────────────┘  └─────────────┘   │
│                                     │    │                                     │
│  ┌─────────────┐  ┌─────────────┐   │    │  ┌─────────────┐  ┌─────────────┐   │
│  │Elasticsearch│  │ Prometheus  │◄──┼────┼──│ Prometheus  │  │   Vector    │   │
│  │   (Logs)    │  │    (CP)     │   │    │  │    (DP)     │  │  (Logging)  │   │
│  └─────────────┘  └─────────────┘   │    │  └─────────────┘  └─────────────┘   │
│                                     │    │                                     │
│  ┌─────────────────────────────┐    │    │  ┌─────────────────────────────┐    │
│  │     CP Nginx Ingress        │    │    │  │     DP Nginx Ingress        │    │
│  └─────────────────────────────┘    │    │  └─────────────────────────────┘    │
└─────────────────────────────────────┘    └─────────────────────────────────────┘
         │                                          │
         │         Cross-cluster communication      │
         └──────────────────────────────────────────┘
```

## Prerequisites

- Docker installed and running
- Python 3.11+ installed
- 30GB+ RAM recommended
- macOS or Linux

---

## Step 1: Install Prerequisites

```bash
# Set this to wherever you cloned astronomer/astronomer; the rest of this guide uses it.
export ASTRONOMER_REPO="${ASTRONOMER_REPO:-$HOME/astronomer/astronomer}"
cd "$ASTRONOMER_REPO"

# Install k3d
curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash

# Or on macOS with Homebrew:
# brew install k3d

# Install helm (if not already installed)
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Verify installations
k3d version
helm version --short
kubectl version --client
```

---

## Step 2: Generate TLS Certificates

```bash
cd "$ASTRONOMER_REPO"

# Install mkcert if not already installed
# macOS: brew install mkcert
# Linux: see https://github.com/FiloSottile/mkcert#installation

# Or use the project's install script
bin/install-ci-tools.py
export PATH="$HOME/.local/share/astronomer-software/bin:$PATH"

# Clean up any old certificates
bin/certs.py cleanup

# Generate TLS certificate for *.localtest.me domain
bin/certs.py generate-tls

# IMPORTANT (Dataplane subdomains + TLS):
# `*.localtest.me` does NOT cover `commander.dp01.localtest.me` (wildcards only match ONE label).
# If you are using a dataplane domainPrefix like `dp01`, you must generate a cert that also covers:
# - dp01.localtest.me
# - *.dp01.localtest.me
#
# Quick way (recommended): regenerate the TLS cert/key with the extra SANs using mkcert directly,
# then re-apply the `astronomer-tls` secret in BOTH clusters.
#
# NOTE: this overwrites the astronomer TLS cert/key created above.
CERT_DIR="$HOME/.local/share/astronomer-software/certs"
MKCERT="$HOME/.local/share/astronomer-software/bin/mkcert"

$MKCERT -install
$MKCERT \
  -cert-file="${CERT_DIR}/astronomer-tls.pem" \
  -key-file="${CERT_DIR}/astronomer-tls.key" \
  localtest.me "*.localtest.me" \
  dp01.localtest.me "*.dp01.localtest.me"

# Append mkcert root CA so `astronomer-tls.pem` is a full chain (matches what `bin/certs.py` does)
CAROOT="$($MKCERT -CAROOT)"
cat "${CAROOT}/rootCA.pem" >> "${CERT_DIR}/astronomer-tls.pem"

# NOTE: `bin/certs.py generate-tls` uses `mkcert` and appends mkcert's root CA to `astronomer-tls.pem`.
# For pods to trust that certificate chain (including the JWKS hook), we need to provide mkcert's *rootCA.pem*
# to the platform via `global.privateCaCerts` (see Step 5).

# Verify certificates were created
ls -la ~/.local/share/astronomer-software/certs/

# Locate mkcert root CA (this is what pods must trust)
MKCERT_CAROOT="$($HOME/.local/share/astronomer-software/bin/mkcert -CAROOT)"
MKCERT_ROOT_CA="${MKCERT_CAROOT}/rootCA.pem"
echo "mkcert CAROOT: ${MKCERT_CAROOT}"
ls -la "${MKCERT_ROOT_CA}"
```

### Apply updated TLS secret to both clusters

If you regenerated the TLS cert/key (for `dp01.localtest.me` + `*.dp01.localtest.me`), update the `astronomer-tls` secret in both clusters:

```bash
for CTX in k3d-control k3d-data; do
  kubectl --context "$CTX" -n astronomer create secret tls astronomer-tls \
    --cert="$HOME/.local/share/astronomer-software/certs/astronomer-tls.pem" \
    --key="$HOME/.local/share/astronomer-software/certs/astronomer-tls.key" \
    --dry-run=client -o yaml | kubectl apply -f -
done

# Restart nginx in both clusters to reload the updated certificate
kubectl --context k3d-control -n astronomer rollout restart deployment -l tier=nginx
kubectl --context k3d-data -n astronomer rollout restart deployment -l tier=nginx
```

---

## Step 3: Create k3d Clusters

k3d uses Flannel by default, which properly routes traffic to external networks.

> **IMPORTANT: CA trust in pods vs nodes**
>
> - **Pods trusting Houston's TLS**: handled by Astronomer via `global.privateCaCerts` (Step 5). This is what fixes the `commander-jwks-hook` SSL verify failure.
> - **Nodes/containerd trusting a private registry**: optional. You can mount a CA into the k3d nodes with `--volume` (useful for **image pulls** from a registry with a private CA), but it’s not required for the platform’s in-pod TLS verification when `global.privateCaCerts` is set.

```bash
# Delete any existing clusters with these names
k3d cluster delete control 2>/dev/null || true
k3d cluster delete data 2>/dev/null || true

# mkcert root CA path (generated in Step 2)
MKCERT_CAROOT="$($HOME/.local/share/astronomer-software/bin/mkcert -CAROOT)"
MKCERT_ROOT_CA="${MKCERT_CAROOT}/rootCA.pem"

# Create Control Plane cluster
# --network: puts both clusters on the same Docker network
# --port: maps container ports to host for external access
k3d cluster create control \
  --network astronomer-net \
  --port "8443:443@loadbalancer" \
  --port "8080:80@loadbalancer" \
  --volume "${MKCERT_ROOT_CA}:/etc/ssl/certs/mkcert-rootCA.pem@server:*" \
  --k3s-arg "--disable=traefik@server:0"

# Create Data Plane cluster on the same network
k3d cluster create data \
  --network astronomer-net \
  --port "8444:443@loadbalancer" \
  --port "8081:80@loadbalancer" \
  --volume "${MKCERT_ROOT_CA}:/etc/ssl/certs/mkcert-rootCA.pem@server:*" \
  --k3s-arg "--disable=traefik@server:0"

# Verify clusters are running
k3d cluster list

# Check contexts
kubectl config get-contexts
```

### (Optional) Make the k3d *nodes* trust mkcert root CA

Mounting the file into `/etc/ssl/certs/` makes it available on the node filesystem, but **some node utilities only trust** `/etc/ssl/certs/ca-certificates.crt`.

If you need the node itself to trust mkcert (for example, debugging from inside the node container), append it to the node CA bundle:

```bash
# Append mkcert root CA into the node CA bundle (Control Plane + Data Plane nodes)
docker exec k3d-control-server-0 sh -c 'cat /etc/ssl/certs/mkcert-rootCA.pem >> /etc/ssl/certs/ca-certificates.crt'
docker exec k3d-data-server-0 sh -c 'cat /etc/ssl/certs/mkcert-rootCA.pem >> /etc/ssl/certs/ca-certificates.crt'

# Verify the file exists
docker exec k3d-control-server-0 ls -la /etc/ssl/certs/mkcert-rootCA.pem
docker exec k3d-data-server-0 ls -la /etc/ssl/certs/mkcert-rootCA.pem
```

> **Note:** This optional node-level trust does **not** replace Step 5. Pods trust Houston’s TLS via `global.privateCaCerts` and the chart’s `update-ca-certificates` step.

The clusters will have contexts named `k3d-control` and `k3d-data`.

---

## Step 4: Get Cluster Node IPs

```bash
# Get Control Plane node IP
CP_NODE_IP=$(docker inspect k3d-control-server-0 -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
echo "Control Plane Node IP: $CP_NODE_IP"

# Get Data Plane node IP
DP_NODE_IP=$(docker inspect k3d-data-server-0 -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
echo "Data Plane Node IP: $DP_NODE_IP"

# Get Docker network subnet
docker network inspect astronomer-net -f '{{range .IPAM.Config}}{{.Subnet}} {{end}}'
```

---

## Step 5: Create Namespaces and Secrets

### Control Plane Cluster

```bash
# Create namespace
kubectl --context k3d-control create namespace astronomer

# Create TLS secret
kubectl --context k3d-control -n astronomer create secret tls astronomer-tls \
  --cert=$HOME/.local/share/astronomer-software/certs/astronomer-tls.pem \
  --key=$HOME/.local/share/astronomer-software/certs/astronomer-tls.key

# Create mkcert root CA secret (CRITICAL: enables pods to trust the self-signed TLS chain)
MKCERT_CAROOT="$($HOME/.local/share/astronomer-software/bin/mkcert -CAROOT)"
MKCERT_ROOT_CA="${MKCERT_CAROOT}/rootCA.pem"
kubectl --context k3d-control -n astronomer create secret generic mkcert-root-ca \
  --from-file=cert.pem="${MKCERT_ROOT_CA}"

# Verify secrets
kubectl --context k3d-control -n astronomer get secrets
```

### Data Plane Cluster

```bash
# Create namespace
kubectl --context k3d-data create namespace astronomer

# Create TLS secret
kubectl --context k3d-data -n astronomer create secret tls astronomer-tls \
  --cert=$HOME/.local/share/astronomer-software/certs/astronomer-tls.pem \
  --key=$HOME/.local/share/astronomer-software/certs/astronomer-tls.key

# Create mkcert root CA secret (CRITICAL: enables pods to trust the self-signed TLS chain)
MKCERT_CAROOT="$($HOME/.local/share/astronomer-software/bin/mkcert -CAROOT)"
MKCERT_ROOT_CA="${MKCERT_CAROOT}/rootCA.pem"
kubectl --context k3d-data -n astronomer create secret generic mkcert-root-ca \
  --from-file=cert.pem="${MKCERT_ROOT_CA}"

# Verify secrets
kubectl --context k3d-data -n astronomer get secrets
```

---

## Step 6: Create Helm Values Files

### Control Plane Values

```bash
cat > /tmp/cp-values.yaml << 'EOF'
# Control Plane Helm Values for k3d
global:
  baseDomain: localtest.me
  plane:
    # mode: control matches the CP/DP architecture in this guide. Use mode: unified
    # only if you intentionally want CP + DP components in one cluster.
    mode: control
    domainPrefix: ""
  tlsSecret: astronomer-tls
  postgresqlEnabled: true
  prometheusPostgresExporterEnabled: true
  privateCaCerts:
    # Trust mkcert root CA so pods (including JWKS hook) can validate Houston's TLS chain
    - mkcert-root-ca
  nats:
    enabled: true
    replicas: 1
  # Disable network policies (k3d/Flannel doesn't support them by default)
  networkPolicy:
    enabled: false
  defaultDenyNetworkPolicy: false
  # Feature flags
  deployRollbackEnabled: true
  taskUsageMetricsEnabled: true
  # Logging stack (Vector daemonset on each cluster, Elasticsearch on the CP)
  daemonsetLogging:
    enabled: true
  elasticsearchEnabled: true
  dagOnlyDeployment:
    enabled: true

tags:
  platform: true
  logging: true
  monitoring: true
  postgresql: true
  nats: true

astronomer:
  astroUI:
    replicas: 1
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
  houston:
    replicas: 1
    worker:
      replicas: 1
    resources:
      requests:
        cpu: "250m"
        memory: "512Mi"
    config:
      # Use flat Boolean form for these two fields — the nested form
      # (publicSignups: { enabled: false }) trips a resolver bug in Houston
      # 1.1.x where AuthConfig.publicSignup is declared Boolean but the
      # resolver returns the wrapper object, breaking the login page.
      emailConfirmation: false
      publicSignups: false
      cors:
        allowedOrigins:
          - "https://app.localtest.me"
      auth:
        local:
          enabled: true
      deployments:
        configureDagDeployment: true
        hardDeleteDeployment: true
  commander:
    replicas: 1
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
  registry:
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"

nginx:
  replicas: 1
  replicasDefaultBackend: 1
  resources:
    requests:
      cpu: "250m"
      memory: "512Mi"

prometheus:
  replicas: 1
  resources:
    requests:
      cpu: "250m"
      memory: "1Gi"

elasticsearch:
  common:
    env:
      NUMBER_OF_MASTERS: "1"

  master:
    replicas: 1
    heapMemory: 256m
    resources:
      requests:
        memory: 512Mi

  data:
    replicas: 1
    heapMemory: 512m
    resources:
      requests:
        memory: 1Gi

  client:
    replicas: 1
    heapMemory: 256m
    resources:
      requests:
        memory: 512Mi
  images:
    es:
      repository: docker.elastic.co/elasticsearch/elasticsearch
      tag: "8.18.6"

nats:
  cluster:
    enabled: false
    replicas: 1
  resources:
    requests:
      cpu: "50m"
      memory: "64Mi"

grafana:
  resources:
    requests:
      cpu: "100m"
      memory: "256Mi"
EOF
```

### Data Plane Values

```bash
cat > /tmp/dp-values.yaml << 'EOF'
global:
  baseDomain: localtest.me
  plane:
    mode: data
    domainPrefix: dp01
  tlsSecret: astronomer-tls
  postgresqlEnabled: true
  prometheusPostgresExporterEnabled: true
  privateCaCerts:
    # Trust mkcert root CA so pods (including JWKS hook) can validate Houston's TLS chain
    - mkcert-root-ca
  nats:
    enabled: true
    replicas: 1
  # Disable network policies (k3d/Flannel doesn't support them by default)
  networkPolicy:
    enabled: false
  defaultDenyNetworkPolicy: false
  # Feature flags
  deployRollbackEnabled: true
  taskUsageMetricsEnabled: true
  # Vector ships per-deployment Airflow logs from this DP to the CP's
  # Elasticsearch via the cross-cluster ES hostname (configured in Step 8).
  daemonsetLogging:
    enabled: true
  dagOnlyDeployment:
    enabled: true

tags:
  platform: true
  logging: true
  monitoring: true
  postgresql: true
  nats: true

astronomer:
  commander:
    replicas: 1
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
  registry:
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"

nginx:
  replicas: 1
  replicasDefaultBackend: 1
  resources:
    requests:
      cpu: "250m"
      memory: "512Mi"

prometheus:
  replicas: 1
  resources:
    requests:
      cpu: "250m"
      memory: "1Gi"

nats:
  cluster:
    enabled: false
    replicas: 1
  resources:
    requests:
      cpu: "50m"
      memory: "64Mi"
EOF
```

---

## Step 7: Install Astronomer Control Plane

```bash
cd "$ASTRONOMER_REPO"

# Update helm dependencies
helm dependency update .

# Install Control Plane
echo "Installing Astronomer Control Plane..."
helm install astronomer . \
  --namespace astronomer \
  --kube-context k3d-control \
  --values /tmp/cp-values.yaml \
  --timeout 60m \
  --wait --debug
```

### Verify Control Plane is Running

```bash
# Check all CP pods are running
kubectl --context k3d-control -n astronomer get pods

# Get CP nginx service
kubectl --context k3d-control -n astronomer get svc astronomer-cp-nginx
```

Wait until all pods show `Running` or `Completed` status before proceeding.

---

## Step 8: Configure DNS for Cross-Cluster Communication

With k3d/Flannel, pods CAN reach external IPs. We just need to configure DNS.

The repo ships a helper script that pins the right IPs in **both** clusters' CoreDNS
`NodeHosts` and in the DP node container's `/etc/hosts` (the latter matters for
kubelet/containerd image pulls, which do NOT use CoreDNS):

```bash
cd "$ASTRONOMER_REPO"
python3 bin/reconcile-k3d-orbstack-network.py
```

The script is idempotent and re-runnable. Use it now (before DP install in Step 9)
so that DP pods boot with working name resolution to Houston, and re-run it any
time OrbStack restarts (see Troubleshooting → "OrbStack restart breaks CP/DP
networking").

### Verify DNS and connectivity from DP

```bash
# Test DNS resolution
kubectl --context k3d-data run test-dns --rm -it --restart=Never --image=busybox -- nslookup houston.localtest.me

# Test actual connectivity from inside the DP cluster
kubectl --context k3d-data run test-curl --rm -it --restart=Never --image=curlimages/curl -- \
  curl -v -k --connect-timeout 10 https://houston.localtest.me/v1/healthz

# IMPORTANT: The registry uses https://houston.<baseDomain>/v1/registry/authorization for OAuth tokens (no port),
# so this must NOT be a 404 from the DP cluster:
kubectl --context k3d-data run test-curl --rm -it --restart=Never --image=curlimages/curl -- \
  curl -v -k --connect-timeout 10 "https://houston.localtest.me/v1/registry/authorization"
```

**Expected result for** `/v1/registry/authorization`:
- A bare request often returns **`401`**, which is OK (it means the endpoint exists and is protected).
- The critical thing is: it must **NOT** be `404`. A `404` here will break DP registry auth and image pulls.

<details>
<summary>Manual fallback: edit CoreDNS by hand</summary>

If the helper script doesn't fit your setup, you can edit each cluster's CoreDNS
`NodeHosts` directly. k3d's CoreDNS uses the `hosts` plugin reading from
`data.NodeHosts` in the `kube-system/coredns` ConfigMap; do **not** add a second
`hosts` block — CoreDNS rejects two `hosts` plugins in the same server block.

```bash
# Get the CP nginx LB IP and DP node IP
CP_NGINX_LB_IP=$(kubectl --context k3d-control -n astronomer get svc astronomer-cp-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
DP_NODE_IP=$(docker inspect k3d-data-server-0 -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')

# DP CoreDNS: pin CP hostnames -> CP nginx LB IP
kubectl --context k3d-data -n kube-system edit configmap coredns
# add to data.NodeHosts:
#   <CP_NGINX_LB_IP> localtest.me houston.localtest.me app.localtest.me grafana.localtest.me

# CP CoreDNS: pin DP hostnames -> DP node IP
kubectl --context k3d-control -n kube-system edit configmap coredns
# add to data.NodeHosts:
#   <DP_NODE_IP> dp01.localtest.me deployments.dp01.localtest.me registry.dp01.localtest.me commander.dp01.localtest.me elasticsearch.dp01.localtest.me prom-proxy.dp01.localtest.me prometheus.dp01.localtest.me

# Restart CoreDNS in both clusters
kubectl --context k3d-data    -n kube-system delete pod -l k8s-app=kube-dns
kubectl --context k3d-control -n kube-system delete pod -l k8s-app=kube-dns
```

After OrbStack restart, the IPs change and the manual edits go stale. The helper
script handles this correctly; the manual flow does not.

</details>

---

## Step 9: Install Astronomer Data Plane

```bash
# Install Data Plane
echo "Installing Astronomer Data Plane..."
helm install astronomer . \
  --namespace astronomer \
  --kube-context k3d-data \
  --values /tmp/dp-values.yaml \
  --timeout 60m \
  --wait --debug
```

---

## Step 10: Verify CP -> DP Connectivity

The reconcile script in Step 8 already pinned DP hostnames in CP's CoreDNS, so
Houston (CP) can call commander (DP). Verify:

```bash
# DNS resolution from inside CP
kubectl --context k3d-control run test-dns --rm -it --restart=Never --image=busybox -- nslookup commander.dp01.localtest.me

# TLS connectivity from inside CP
kubectl --context k3d-control run test-curl --rm -it --restart=Never --image=curlimages/curl -- \
  curl -v -k --connect-timeout 10 https://commander.dp01.localtest.me/healthz
```

If either fails, re-run `python3 bin/reconcile-k3d-orbstack-network.py` from
`$ASTRONOMER_REPO`.

---

## Step 11: Configure Local Machine DNS

The URLs Houston builds for the UI's "Open Airflow" link (and similar) are
port-less — `https://deployments.dp01.localtest.me/<release>/airflow`. For those
links to work in your browser without manual edits, your host needs to resolve
each hostname to an IP that already serves on `:443`. On OrbStack, that's the
LB IP of each cluster's nginx — so we map hostnames to those IPs in `/etc/hosts`.

### Option A (recommended): map hostnames to k3d LoadBalancer IPs

This works on OrbStack because OrbStack auto-routes the docker subnet to the
host. Each cluster's nginx serves its own `:443`, so the browser reaches CP and
DP on standard ports without any port-mapping or SNI demux.

```bash
# Look up the LB IPs
CP_NGINX_LB_IP=$(kubectl --context k3d-control -n astronomer get svc astronomer-cp-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
DP_NGINX_LB_IP=$(kubectl --context k3d-data    -n astronomer get svc astronomer-dp-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "CP nginx LB IP: $CP_NGINX_LB_IP"
echo "DP nginx LB IP: $DP_NGINX_LB_IP"

# Confirm your host can route to them (expect HTTP/2 200 from each)
curl -vk --connect-timeout 3 "https://${CP_NGINX_LB_IP}/healthz" 2>&1 | grep -E "^< HTTP"
curl -vk --connect-timeout 3 "https://${DP_NGINX_LB_IP}/healthz" 2>&1 | grep -E "^< HTTP"

# If both succeed, append to /etc/hosts:
sudo bash -c "cat <<EOF >> /etc/hosts

# === astronomer local-k3d (LB-IP routing) ===
${CP_NGINX_LB_IP} localtest.me app.localtest.me houston.localtest.me grafana.localtest.me
${DP_NGINX_LB_IP} dp01.localtest.me deployments.dp01.localtest.me registry.dp01.localtest.me commander.dp01.localtest.me
EOF"
```

You can now access the platform port-less:

- UI: `https://app.localtest.me`
- Houston: `https://houston.localtest.me`
- Per-deployment Airflow: `https://deployments.dp01.localtest.me/<release-name>/airflow/`
- Astro CLI: `astro login https://houston.localtest.me`

### Option B (fallback): host-mapped ports

If the routability check above fails (some Docker Desktop or non-OrbStack
configurations don't expose the docker subnet to the host), fall back to host
port-forwarding via the `--port` mappings from Step 3. You will need to type
`:8443` / `:8444` in URLs manually, and Houston's "Open Airflow" link won't
work without a per-dataplane `baseDomain` override or an SNI reverse-proxy on
host `:443`.

```bash
sudo bash -c 'echo "127.0.0.1 localtest.me app.localtest.me houston.localtest.me grafana.localtest.me" >> /etc/hosts'
sudo bash -c 'echo "127.0.0.1 dp01.localtest.me deployments.dp01.localtest.me registry.dp01.localtest.me commander.dp01.localtest.me" >> /etc/hosts'
```

Then access via:

- UI: `https://app.localtest.me:8443`
- Per-deployment Airflow: `https://deployments.dp01.localtest.me:8444/<release-name>/airflow/`
- Astro CLI: `astro login https://houston.localtest.me:8443`

---

## Step 12: Verify Installation

### Check Pods

```bash
echo "=== Control Plane Pods ==="
kubectl --context k3d-control -n astronomer get pods

echo ""
echo "=== Data Plane Pods ==="
kubectl --context k3d-data -n astronomer get pods
```

### Test Cross-Cluster Communication

```bash
# From DP pod, test connectivity to CP
kubectl --context k3d-data run test-curl --rm -it --restart=Never --image=curlimages/curl -- \
  curl -k https://houston.localtest.me/v1/healthz

# From CP pod, test connectivity to DP
kubectl --context k3d-control run test-curl --rm -it --restart=Never --image=curlimages/curl -- \
  curl -k https://dp01.localtest.me/healthz
```

---

## Step 13: Access the Platform

### Access URLs

If you used Option A in Step 11 (LB-IP routing — recommended):

| Component | URL |
|-----------|-----|
| Astro UI (CP) | https://app.localtest.me |
| Houston API (CP) | https://houston.localtest.me |
| Grafana (CP) | https://grafana.localtest.me |
| Deployments (DP) | https://deployments.dp01.localtest.me |
| Registry (DP) | https://registry.dp01.localtest.me |

If you used Option B (host-mapped ports), append `:8443` for CP and `:8444`
for DP hostnames.

> **Note**: Because the certificates are mkcert-signed, your browser should
> trust them automatically once `mkcert -install` has been run (Step 2). If
> you see a warning, re-run `mkcert -install` or accept the self-signed cert.

---

## Troubleshooting

### OrbStack restart breaks CP/DP networking (k3d)

If CP/DP communication “randomly” breaks **after restarting OrbStack**, it’s usually **not CoreDNS crashing** — it’s **stale name→IP pinning**:

- Pods resolve cross-cluster names via **CoreDNS** (`kube-system/configmap/coredns` → `data.NodeHosts`)
- Node-level operations (notably **kubelet/containerd image pulls**) resolve via the **k3d node container’s `/etc/hosts` / DNS**, **not** CoreDNS
- After an OrbStack restart, k3d node container IPs and/or k3s Service `LoadBalancer` IPs can change, and Docker may regenerate container `/etc/hosts`

**Fix (recommended):** re-sync the pinned entries and restart CoreDNS using the helper script:

```bash
cd "$ASTRONOMER_REPO"
python3 bin/reconcile-k3d-orbstack-network.py
```

Defaults assumed by the script:
- CP context: `k3d-control`
- DP context: `k3d-data`
- Namespace: `astronomer`
- Base domain: `localtest.me`
- DP domain prefix: `dp01`

Override via env vars (example):

```bash
CP_CONTEXT=k3d-control \
DP_CONTEXT=k3d-data \
BASE_DOMAIN=localtest.me \
DP_DOMAIN_PREFIX=dp01 \
python3 bin/reconcile-k3d-orbstack-network.py
```

**Quick checks**

```bash
# Has the CP ingress LB IP changed?
kubectl --context k3d-control -n astronomer get svc astronomer-cp-nginx

# Can a DP pod still reach Houston?
kubectl --context k3d-data run test-curl --rm -it --restart=Never --image=curlimages/curl -- \
  curl -vk -k --connect-timeout 5 https://houston.localtest.me/v1/healthz

# Does the DP node container resolve Houston correctly (node-level DNS)?
docker exec k3d-data-server-0 sh -c 'grep -n "houston.localtest.me" /etc/hosts || true'
```

### Browser works but CLI (`astro`, `curl`) fails

If the browser can load `https://houston.localtest.me` but `astro login localtest.me` fails, it usually means the
browser and CLI are **not connecting to the same IP:port**.

- **Common causes**
  - **Different port**: you tested `https://houston.localtest.me:8443` in the browser, but the CLI is trying `:443`.
  - **Different DNS path**: Chrome/Edge can use **DNS-over-HTTPS (Secure DNS)**, bypassing `/etc/hosts`, while Go-based CLIs
    (Astro CLI) use the OS resolver and `/etc/hosts`.
  - **IPv6 vs IPv4**: the hostname resolves to both `::1` and `127.0.0.1`, and the CLI picks `::1` first.
  - **OrbStack routing**: the hostname resolves to a k3d “EXTERNAL-IP” like `192.168.147.2`, but your macOS host cannot route to it
    (you’ll see `No route to host`).

- **Quick checks**

```bash
# What does macOS think it resolves to (hosts + DNS + cache)?
dscacheutil -q host -a name houston.localtest.me

# What IP:port is the CLI trying?
curl -vk --connect-timeout 3 https://houston.localtest.me/v1/healthz

# For Astro CLI (Go), show which resolver path it uses:
GODEBUG=netdns=go+1 astro login localtest.me
```

- **Fixes that reliably work on OrbStack**
  - **Recommended**: use Step 11 Option A (LB-IP routing). Hostnames resolve
    directly to each cluster's nginx LB IP and serve on `:443` natively, so
    browsers and CLIs hit the same endpoint without port hackery.
  - **If you stayed on Option B (host-mapped ports)**: pass the port to the
    CLI explicitly, e.g. `astro login https://houston.localtest.me:8443`.

If you want the browser to follow `/etc/hosts`, disable Secure DNS in your browser settings or test with `curl` (which uses the OS resolver).

### Registry push/pull fails with `failed to fetch oauth token ... /v1/registry/authorization ... 404`

If you see errors like:

- `failed to authorize: failed to fetch oauth token: unexpected status from GET request to https://houston.<baseDomain>/v1/registry/authorization ... 404`

This can show up as:
- **Airflow image pull failures** (kubelet/containerd can’t authorize to pull from `registry.dp01.<baseDomain>`)
- **Docker push/pull failures** to the platform registry

If a **pod** in the Data Plane can reach Houston, the problem is usually **node-level DNS**, not CoreDNS:

- Pods use **CoreDNS** (your `NodeHosts` edits).
- Image pulls are performed by **kubelet/containerd on the k3d node container**, which uses the node’s DNS and `/etc/hosts`.

**Check from the DP node container**:

```bash
docker exec k3d-data-server-0 sh -c 'nslookup houston.localtest.me || true'
```

If it resolves to `127.0.0.1` / `::1`, fix it by pinning `houston.localtest.me` to the **CP nginx LoadBalancer IP** in the node’s `/etc/hosts`:

```bash
CP_NGINX_LB_IP=$(kubectl --context k3d-control -n astronomer get svc astronomer-cp-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
docker exec k3d-data-server-0 sh -c "echo \"$CP_NGINX_LB_IP houston.localtest.me\" >> /etc/hosts"

# Verify: should be 401 (or 403), but NOT 404
docker exec k3d-data-server-0 sh -c 'apk add --no-cache curl >/dev/null 2>&1 || true; curl -4sk --connect-timeout 3 -o /dev/null -w "%{http_code}\n" "https://houston.localtest.me/v1/registry/authorization?service=docker-registry&scope=repository:test/test:pull"'
```

For a permanent solution, recreate k3d clusters using k3d’s host-alias support so these `/etc/hosts` entries are injected at cluster creation time.

### `helm install` hung or failed: stuck `pending-install` release

If `helm install --wait` times out, the release sits in `pending-install` and
subsequent installs fail with `cannot re-use a name that is still in use` or
`release exists`. Clean up before retrying:

```bash
# Replace <ctx> with k3d-control or k3d-data depending on which install hung.
helm --kube-context <ctx> -n astronomer status astronomer | head
helm --kube-context <ctx> -n astronomer uninstall astronomer

# If uninstall complains the release is in pending-install, force it:
kubectl --context <ctx> -n astronomer delete secret -l owner=helm,name=astronomer

# Then retry the install from Step 7 / Step 9.
```

### Pods can't find the `astronomer-bootstrap` secret

If you see `secret "astronomer-bootstrap" not found` in init containers, the
**postgres subchart didn't deploy successfully**. The bootstrap secret is
generated by the postgres subchart's hooks; if postgres failed to deploy, the
secret doesn't exist and downstream pods stall. Don't create the secret
manually — fix postgres first:

```bash
# Check postgres pod and logs
kubectl --context <ctx> -n astronomer get pods -l role=astronomer-postgresql
kubectl --context <ctx> -n astronomer logs astronomer-postgresql-0 --previous

# Common causes: subchart conditions disabled (check `global.postgresqlEnabled: true`
# in your values file), or the persistent volume claim got stuck.
```

### View Pod Logs

```bash
# Control Plane Houston logs
kubectl --context k3d-control -n astronomer logs -l component=houston -f

# Data Plane Commander logs
kubectl --context k3d-data -n astronomer logs -l component=commander -f
```

### Delete and Recreate

```bash
# Delete helm releases
helm --kube-context k3d-control uninstall astronomer -n astronomer
helm --kube-context k3d-data uninstall astronomer -n astronomer

# Delete clusters entirely
k3d cluster delete control
k3d cluster delete data
```

---

## Key Differences from kind Setup

| Aspect | kind + Calico | k3d + Flannel |
|--------|---------------|---------------|
| CNI | Calico | Flannel |
| Network Policies | ✅ Supported | ❌ Disabled |
| Pod-to-external routing | ❌ Problematic | ✅ Works |
| Cross-cluster communication | Complex | Simple |
| Setup complexity | Higher | Lower |

**Trade-off**: k3d setup is simpler but doesn't support network policies. For local development and testing CP/DP communication, this is acceptable. For production, use proper Kubernetes clusters with full CNI support.
