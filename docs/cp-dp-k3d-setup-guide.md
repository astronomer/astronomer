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
# Navigate to the astronomer directory
cd /Users/karankhanchandani/codebase/python/astronomer

# Activate the existing virtual environment
source venv/bin/activate

# Install required Python packages
pip install -r tests/requirements.in

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
cd /Users/karankhanchandani/codebase/python/astronomer

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
# Control Plane Helm Values for k3d
global:
  baseDomain: localtest.me
  plane:
    mode: unified
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
  # For local k3d: keep logging disabled (Elasticsearch fails in k3d due to seccomp limitations)
  vectorEnabled: true
  elasticsearchEnabled: true
  dagOnlyDeployment:
    enabled: true

tags:
  platform: true
  # For local k3d: disable logging to avoid Elasticsearch/seccomp issues
  logging: true
  monitoring: true
  postgresql: true
  nats: true

astronomer:
  astroUI:
    replicas: 1
    # Explicitly set API endpoints used by the UI (useful when running behind custom DNS/ports)
    env:
      - name: APP_API_LOC_HTTPS
        value: "https://houston.localtest.me/v1"
      - name: APP_API_LOC_WSS
        value: "wss://houston.localtest.me/ws"
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
  # For local k3d: keep logging disabled (Elasticsearch fails in k3d due to seccomp limitations)
  vectorEnabled: true
  dagOnlyDeployment:
    enabled: true

tags:
  platform: true
  # For local k3d: disable logging to avoid Elasticsearch/seccomp issues
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

vector:
  enabled: true

nats:
  cluster:
    enabled: false
    replicas: 1
  resources:
    requests:
      cpu: "50m"
      memory: "64Mi"


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
EOF
```

---

## Step 7: Install Astronomer Control Plane

```bash
cd /Users/karankhanchandani/codebase/python/astronomer

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

### Get Control Plane ingress IP (for DP -> CP calls)

```bash
# IMPORTANT: Use the Control Plane nginx LoadBalancer IP for inter-cluster calls.
# Do NOT use the node container IP, otherwise you may hit the wrong ingress and get 404s for Houston endpoints.
CP_NGINX_LB_IP=$(kubectl --context k3d-control -n astronomer get svc astronomer-cp-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "CP nginx LoadBalancer IP: $CP_NGINX_LB_IP"
```

### Configure CoreDNS in Data Plane

> **IMPORTANT:** k3d's CoreDNS uses a `hosts` plugin that reads from the `NodeHosts` data in the ConfigMap.
> Do NOT add a second `hosts` block - CoreDNS doesn't allow two `hosts` plugins in the same server block.
> Instead, add your custom entries to the `NodeHosts` section.

```bash
# Backup CoreDNS ConfigMap
kubectl --context k3d-data -n kube-system get configmap coredns -o yaml > /tmp/coredns-dp-backup.yaml

# Create the coredns-custom ConfigMap if it doesn't exist (required by k3d)
kubectl --context k3d-data -n kube-system create configmap coredns-custom 2>/dev/null || true

# Edit CoreDNS ConfigMap
kubectl --context k3d-data -n kube-system edit configmap coredns
```

Add your custom DNS entries to the `NodeHosts` section (at the end of the data section):

```yaml
data:
  Corefile: |
    .:53 {
        errors
        health
        ready
        kubernetes cluster.local in-addr.arpa ip6.arpa {
          pods insecure
          fallthrough in-addr.arpa ip6.arpa
        }
        hosts /etc/coredns/NodeHosts {
          ttl 60
          reload 15s
          fallthrough
        }
        prometheus :9153
        cache 30
        loop
        reload
        loadbalance
        import /etc/coredns/custom/*.override
        forward . /etc/resolv.conf
    }
    import /etc/coredns/custom/*.server
  NodeHosts: |
    192.168.147.1 host.k3d.internal
    192.168.147.4 k3d-data-serverlb
    192.168.147.5 k3d-control-serverlb
    192.168.147.2 k3d-data-server-0
    192.168.147.3 k3d-control-server-0
    <CP_NGINX_LB_IP> localtest.me houston.localtest.me app.localtest.me grafana.localtest.me
```

Replace `<CP_NGINX_LB_IP>` with the actual CP nginx LoadBalancer IP (e.g., `192.168.147.2`).

> **Note:** The existing NodeHosts entries will vary based on your k3d setup. Just add your custom line at the end.

```bash
# Restart CoreDNS to pick up changes
kubectl --context k3d-data -n kube-system delete pod -l k8s-app=kube-dns
kubectl --context k3d-data -n kube-system wait --for=condition=ready pod -l k8s-app=kube-dns --timeout=60s
```

### Verify DNS and Connectivity from DP

```bash
# Test DNS resolution
kubectl --context k3d-data run test-dns --rm -it --restart=Never --image=busybox -- nslookup houston.localtest.me

# Test actual connectivity (this should work with k3d!)
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

## Step 10: Configure CP CoreDNS to Reach DP

```bash
# Get DP node IP
DP_NODE_IP=$(docker inspect k3d-data-server-0 -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
echo "DP Node IP: $DP_NODE_IP"

# Create the coredns-custom ConfigMap if it doesn't exist (required by k3d)
kubectl --context k3d-control -n kube-system create configmap coredns-custom 2>/dev/null || true

# Edit CoreDNS in CP cluster
kubectl --context k3d-control -n kube-system edit configmap coredns
```

Add DP entries to the `NodeHosts` section (same approach as DP cluster):

```yaml
  NodeHosts: |
    ... existing entries ...
    <DP_NODE_IP> dp01.localtest.me registry.dp01.localtest.me commander.dp01.localtest.me elasticsearch.dp01.localtest.me prom-proxy.dp01.localtest.me prometheus.dp01.localtest.me
```

Replace `<DP_NODE_IP>` with the actual DP node IP (e.g., `192.168.147.2`).

```bash
# Restart CoreDNS
kubectl --context k3d-control -n kube-system delete pod -l k8s-app=kube-dns
kubectl --context k3d-control -n kube-system wait --for=condition=ready pod -l k8s-app=kube-dns --timeout=60s
```

---

## Step 11: Configure Local Machine DNS

```bash
# IMPORTANT: host access on OrbStack (macOS)
# - In OrbStack, the k3d "LoadBalancer EXTERNAL-IP" (often 192.168.147.x) may be reachable from OTHER containers,
#   but NOT routable from your macOS host. If you see "No route to host" from the host, this is why.
# - Browsers and CLIs can appear to behave differently if they're resolving to different IPs (DoH / cache / IPv6),
#   or if you're testing in the browser with a host-mapped port (e.g. :8443) but the CLI is trying :443.
#
# Because you are running *two* clusters, you also cannot have both clusters claim host :443 at the same time
# without an SNI reverse-proxy on your host (see Troubleshooting below).

# Option A (recommended on OrbStack): use host-mapped ports
# - Map hostnames to 127.0.0.1
# - Access CP via https://houston.localtest.me:8443 (browser) and DP via https://deployments.dp01.localtest.me:8444
# - For Astro CLI, pass the port explicitly (recommended): `astro login https://houston.localtest.me:8443`
#
# NOTE: This assumes you created clusters with distinct host ports (example):
# - CP: 8443->443, 8080->80
# - DP: 8444->443, 8081->80
sudo bash -c 'echo "127.0.0.1 localtest.me app.localtest.me houston.localtest.me grafana.localtest.me" >> /etc/hosts'
sudo bash -c 'echo "127.0.0.1 dp01.localtest.me deployments.dp01.localtest.me registry.dp01.localtest.me commander.dp01.localtest.me" >> /etc/hosts'

# Optional: if you *must* use https://houston.localtest.me (no port) from your host,
# you need an SNI reverse-proxy on your host that routes:
# - app/houston/grafana -> 127.0.0.1:8443
# - deployments/registry/commander -> 127.0.0.1:8444
#
# A plain `socat` 443->8443 will break DP hostnames on :443 because it can’t route by hostname.
#
# Option B (only if your host can route to the LB IPs): map hostnames to the k3d LoadBalancer IPs
# You can test routability from your macOS host:
#
#   CP_LB_IP=$(kubectl --context k3d-control -n astronomer get svc astronomer-cp-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
#   curl -vk --connect-timeout 3 "https://${CP_LB_IP}/healthz"
#
# If this succeeds, you can map /etc/hosts to the LB IPs and use 443 with no port.
```

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

| Component | URL |
|-----------|-----|
| Astro UI (CP) | https://app.localtest.me:8443 |
| Houston API (CP) | https://houston.localtest.me:8443 |
| Grafana (CP) | https://grafana.localtest.me:8443 |
| Deployments (DP) | https://deployments.dp01.localtest.me:8444 |
| Registry (DP) | https://registry.dp01.localtest.me:8444 |

> **Note**: Accept the certificate warning in your browser (self-signed cert).

---

## Troubleshooting

### OrbStack restart breaks CP/DP networking (k3d)

If CP/DP communication “randomly” breaks **after restarting OrbStack**, it’s usually **not CoreDNS crashing** — it’s **stale name→IP pinning**:

- Pods resolve cross-cluster names via **CoreDNS** (`kube-system/configmap/coredns` → `data.NodeHosts`)
- Node-level operations (notably **kubelet/containerd image pulls**) resolve via the **k3d node container’s `/etc/hosts` / DNS**, **not** CoreDNS
- After an OrbStack restart, k3d node container IPs and/or k3s Service `LoadBalancer` IPs can change, and Docker may regenerate container `/etc/hosts`

**Fix (recommended):** re-sync the pinned entries and restart CoreDNS using the helper script:

```bash
cd /Users/karankhanchandani/codebase/python/astronomer
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
  - **Use the port explicitly**: `astro login https://houston.localtest.me:8443`
  - **Or forward host :443 → :8443**:

```bash
sudo socat TCP-LISTEN:443,fork,reuseaddr TCP:127.0.0.1:8443
```

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
