# Setting Up a Local Astronomer 0.37.x Cluster

## Overview

This guide walks through spinning up a local Astronomer 0.37.x deployment
using a single k3d cluster. This is useful for:

- Testing the 0.37.x-to-2.x upgrade path before applying it to production
- Reproducing issues reported on 0.37.x installations
- Validating the `bin/migrate-helm-chart-values-037x-to-2x.py` migration
  script against a live deployment

The setup script `bin/setup-037x-k3d.py` automates the entire workflow:
TLS cert generation, k3d cluster creation, namespace/secret setup, and Helm
installation of the 0.37.x chart from the remote Astronomer Helm repository.

## Architecture

The 0.37.x chart deploys a single-cluster Astronomer installation with no
control/data plane separation. The deployment includes:

- **Platform**: Houston API, Astro UI, Commander, Registry, Nginx
- **Monitoring**: Prometheus, Grafana, kube-state-metrics, blackbox exporter
- **Logging**: Elasticsearch, Fluentd, Kibana
- **Messaging**: NATS + NATS Streaming (stan)
- **Database**: PostgreSQL (in-cluster, for local use)

## Prerequisites

The following tools must be installed and available in your `PATH`:

- **Docker** (Docker Desktop or OrbStack)
- **k3d** — lightweight Kubernetes in Docker
  ```bash
  brew install k3d
  ```
- **kubectl**
  ```bash
  brew install kubectl
  ```
- **helm** (3.6+)
  ```bash
  brew install helm
  ```
- **mkcert** — local TLS certificate generation
  ```bash
  brew install mkcert
  mkcert -install
  ```

## Quick Start

Run the setup script with defaults to create a cluster named `astro037`
running chart version `0.37.7`:

```bash
python bin/setup-037x-k3d.py
```

The script runs through these milestones:

1. Validates prerequisites (docker, k3d, kubectl, helm)
2. Creates a Docker network (`astronomer-net`)
3. Generates TLS certificates via mkcert
4. Creates a k3d cluster with ports 8443 (HTTPS) and 8080 (HTTP) mapped
5. Creates the `astronomer` namespace, TLS secret, and mkcert root CA secret
6. Adds/updates the Astronomer Helm repository
7. Writes a 0.37.x-schema `values.yaml` with local-friendly resource settings
8. Installs `astronomer/astronomer` chart version 0.37.7
9. Prints `/etc/hosts` entries and access URLs

## Configure /etc/hosts

After the script completes, it prints the required `/etc/hosts` entry. Add
it to your `/etc/hosts` file:

```bash
sudo vi /etc/hosts
```

Add the line printed by the script (example):

```
192.168.205.5 localtest.me app.localtest.me houston.localtest.me grafana.localtest.me kibana.localtest.me prometheus.localtest.me elasticsearch.localtest.me alertmanager.localtest.me registry.localtest.me
```

The actual IP will be the Docker IP of the `k3d-astro037-serverlb` container.

## Access the Deployment

After `/etc/hosts` is configured:

| Service | URL |
|---|---|
| Astro UI | `https://app.localtest.me:8443` |
| Houston API | `https://houston.localtest.me:8443/v1` |
| Grafana | `https://grafana.localtest.me:8443` |
| Kibana | `https://kibana.localtest.me:8443` |

The kubectl context is `k3d-astro037`:

```bash
kubectl --context k3d-astro037 get pods -n astronomer
```

## Configuration Options

### Custom chart version

Install a specific 0.37.x patch release:

```bash
python bin/setup-037x-k3d.py --chart-version 0.37.5
```

### Custom cluster name and ports

Avoid conflicts with other local clusters:

```bash
python bin/setup-037x-k3d.py \
  --cluster-name my037 \
  --https-port 9443 \
  --http-port 9080
```

### Custom base domain

```bash
python bin/setup-037x-k3d.py --base-domain astro.local
```

### Extra Helm values

Pass additional overrides on top of the generated values:

```bash
python bin/setup-037x-k3d.py --helm-values my-overrides.yaml
```

You can repeat `--helm-values` for multiple files.

### Save the generated values file

By default, the script writes values to a temp directory. To save it to a
known location:

```bash
python bin/setup-037x-k3d.py --values-dir ./my-values
# Values are written to ./my-values/values.yaml
```

## Skip Steps (Re-runs)

The script is idempotent. On re-runs, skip steps that already completed:

```bash
# Re-run only the Helm install (certs, cluster, secrets already exist)
python bin/setup-037x-k3d.py --skip-certs --skip-cluster --skip-secrets

# Re-run only secrets + Helm (cluster already exists)
python bin/setup-037x-k3d.py --skip-certs --skip-cluster
```

## Recreate From Scratch

Delete and recreate the cluster:

```bash
python bin/setup-037x-k3d.py --recreate-cluster
```

## Testing the 0.37.x to 2.x Migration

This is the primary use case for this script. After the 0.37.x cluster is
running:

### Step 1: Extract the live values

```bash
helm get values astronomer -n astronomer -o yaml \
  --kube-context k3d-astro037 > current-037x-values.yaml
```

### Step 2: Preview the migration

```bash
./bin/migrate-helm-chart-values-037x-to-2x.py --dry-run current-037x-values.yaml
```

### Step 3: Run the migration

```bash
./bin/migrate-helm-chart-values-037x-to-2x.py --in-place --backup current-037x-values.yaml
```

### Step 4: Review changes

```bash
diff current-037x-values.yaml.bak current-037x-values.yaml
```

### Step 5: Upgrade to 2.x using the local chart

```bash
helm upgrade astronomer . \
  -n astronomer \
  --kube-context k3d-astro037 \
  -f current-037x-values.yaml \
  --timeout 15m \
  --wait
```

### Step 6: Verify

```bash
helm ls -n astronomer --kube-context k3d-astro037
kubectl --context k3d-astro037 get pods -n astronomer
```

See
[Upgrade values.yaml from 0.37.x to 2.x](upgrade-values-migration-037x-to-2x.md)
for the complete migration reference.

## Cleanup

Delete the k3d cluster:

```bash
k3d cluster delete astro037
```

Remove the Docker network (if no other clusters use it):

```bash
docker network rm astronomer-net
```

Remove the `/etc/hosts` entry you added earlier.

## Troubleshooting

### Helm install times out

Increase the timeout:

```bash
python bin/setup-037x-k3d.py --helm-timeout 90m --skip-certs --skip-cluster --skip-secrets
```

Check which pods are not ready:

```bash
kubectl --context k3d-astro037 get pods -n astronomer --field-selector=status.phase!=Running
kubectl --context k3d-astro037 describe pod <failing-pod> -n astronomer
kubectl --context k3d-astro037 logs <failing-pod> -n astronomer
```

### Port conflicts

If ports 8443/8080 are in use, specify different ports:

```bash
python bin/setup-037x-k3d.py --https-port 9443 --http-port 9080
```

### Elasticsearch pods stuck in init

Elasticsearch requires `vm.max_map_count=262144`. On Docker Desktop, this is
usually set. On OrbStack or Linux, you may need:

```bash
# On the host (or inside the OrbStack VM)
sudo sysctl -w vm.max_map_count=262144
```

### Houston pod CrashLoopBackOff

Check Houston logs and the bootstrap secret:

```bash
kubectl --context k3d-astro037 logs deploy/astronomer-houston -n astronomer --tail=50
kubectl --context k3d-astro037 get secret astronomer-bootstrap -n astronomer -o yaml
```

### Cannot reach services after OrbStack restart

Docker container IPs change after OrbStack restarts. Re-check the serverlb IP
and update `/etc/hosts`:

```bash
docker inspect k3d-astro037-serverlb -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```

Update the IP in your `/etc/hosts` file.

## Complete CLI Reference

```
python bin/setup-037x-k3d.py --help
```

| Flag | Default | Description |
|---|---|---|
| `--base-domain` | `localtest.me` | Base domain for all subdomains |
| `--namespace` | `astronomer` | Kubernetes namespace |
| `--release-name` | `astronomer` | Helm release name |
| `--docker-network` | `astronomer-net` | Docker network name |
| `--cluster-name` | `astro037` | k3d cluster name |
| `--https-port` | `8443` | Host HTTPS port mapped to cluster |
| `--http-port` | `8080` | Host HTTP port mapped to cluster |
| `--chart-version` | `0.37.7` | Astronomer chart version to install |
| `--helm-timeout` | `60m` | Helm install timeout |
| `--helm-debug` | off | Enable Helm debug output |
| `--recreate-cluster` | off | Delete and recreate the cluster |
| `--skip-certs` | off | Skip TLS cert generation |
| `--skip-cluster` | off | Skip k3d cluster creation |
| `--skip-secrets` | off | Skip namespace + secret creation |
| `--skip-helm` | off | Skip Helm install |
| `--values-dir` | temp dir | Directory to write generated values.yaml |
| `--helm-values FILE` | none | Extra Helm values file (repeatable) |
