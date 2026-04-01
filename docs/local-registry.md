# Local Pull-Through Registry Cache for k3d Development

This document explains the local Docker registry proxy setup used to speed up k3d cluster creation during local development.

---

## The Problem

Both `bin/setup-037x-k3d.py` and `bin/setup-cp-dp-k3d.py` spin up k3d clusters that pull images directly from remote registries on every run:

| Registry | Images |
|---|---|
| `quay.io` | Astronomer platform images (ap-base, houston, commander, …) |
| `docker.io` | Bitnami, PostgreSQL, MySQL, and other chart dependencies |
| `docker.elastic.co` | Elasticsearch |
| `registry.k8s.io` | k3s system images (pause, coredns, metrics-server, …) |

These registries apply **rate limiting** on anonymous pulls. Because clusters are destroyed and recreated frequently during local development, every cluster creation triggers a full image pull from the internet — leading to slow spin-up times and occasional `Too Many Requests` errors.

---

## The Solution

Four **Docker Registry v2 pull-through caching containers** run as persistent Docker containers outside any k3d cluster. They live on the same Docker network (`astronomer-net`) so that k3d nodes can reach them directly by container name.

```
Docker network: astronomer-net
├── k3d-control-server-0 \
├── k3d-data-1-server-0   }── k3d cluster nodes (destroyed/recreated)
├── ...                  /
│
├── astronomer-registry-proxy-quay     → caches quay.io          (host: localhost:15001)
├── astronomer-registry-proxy-docker   → caches docker.io         (host: localhost:15002)
├── astronomer-registry-proxy-elastic  → caches docker.elastic.co (host: localhost:15003)
└── astronomer-registry-proxy-k8s      → caches registry.k8s.io   (host: localhost:15004)
```

Image cache data lives in named Docker volumes (`astronomer-registry-proxy-*-data`), which persist across Docker daemon restarts.

### How It Works

k3d's `--registry-config` flag injects a containerd mirror configuration into every node at cluster creation time. When a pod or k3s itself pulls an image, containerd checks the local proxy first. On a cache hit the image is served locally; on a miss the proxy fetches it from the upstream registry, caches it, and returns it — so future pulls of the same image are instant.

**The mirror is completely transparent.** Helm values (`image.repository`, `image.tag`, etc.) do not need to change. Image references still point at `quay.io/astronomer/…` — containerd handles the redirect silently.

---

## Design Decisions

### Why four containers instead of one?

Docker Registry v2 can only proxy **one upstream registry per instance**. A single container could cache either `quay.io` or `docker.io`, but not both.

We evaluated two alternatives:

**Option A — zot registry (single container)**

[zot](https://zotregistry.io) is a CNCF OCI registry that supports syncing from multiple upstreams. It would allow a single container to handle all four registries.

*Why we chose not to use it:*

- **Requires explicit prefix mappings.** zot needs to know which upstream to pull from for each image path (e.g., `/astronomer/**` → quay.io). Docker Registry v2 proxy mode forwards everything to its one upstream automatically — no path config needed.
- **Silent cache misses.** If a new image is added to the chart from an unconfigured prefix, zot silently fails to cache it and falls back to a direct pull. With separate proxies, everything from each upstream is automatically cached.
- **Configuration maintenance.** Prefix mappings must be kept in sync with chart changes.
- **Less operational familiarity.** `registry:2` is the industry standard for this pattern; zot in sync mode is less commonly debugged.

**Option B — Four `registry:2` containers (chosen)**

Each container is a simple, zero-config pull-through proxy for one upstream. No prefix configuration, no path mappings, no silent misses. Adding support for a new upstream means adding one more container.

*Trade-offs:*
- Four containers instead of one (~20 MB RAM each when idle).
- Slightly more initial setup (handled automatically by the scripts).

The operational simplicity and correctness of Option B outweigh the aesthetic appeal of a single container.

---

## Usage

### Automatic (recommended)

Both `setup-037x-k3d.py` and `setup-cp-dp-k3d.py` automatically start the registry proxies before creating clusters. No manual action is required.

To skip the local registry (fall back to direct remote pulls):

```bash
python3 bin/setup-037x-k3d.py --no-local-registry
python3 bin/setup-cp-dp-k3d.py --no-local-registry
```

### Standalone Management

Use `bin/setup-local-registry.py` to manage the registry containers independently of cluster creation:

```bash
# Ensure all four registry containers are running
python3 bin/setup-local-registry.py

# Show current container status
python3 bin/setup-local-registry.py --status

# Use a custom Docker network
python3 bin/setup-local-registry.py --docker-network my-net

# Stop and remove containers (cache volumes are kept)
python3 bin/setup-local-registry.py --destroy

# Stop, remove containers AND purge all cached image data
python3 bin/setup-local-registry.py --destroy --purge
```

### Pulling Images Directly from Host

The containers expose their ports on localhost, so you can pull from the cache directly from your host machine:

```bash
# Pull an Astronomer image through the local quay.io proxy
docker pull localhost:15001/astronomer/ap-base:latest

# Pull an Elasticsearch image through the local elastic proxy
docker pull localhost:15003/elasticsearch/elasticsearch:8.18.6
```

This is useful for pre-warming the cache before cluster creation (see below).

---

## Pre-Warming the Cache

On first run, the proxy containers have an empty cache and will pull each image from the internet on demand. Subsequent cluster creations will use the cached images. If you want to pre-warm specific images before cluster creation:

```bash
# Warm the quay.io cache (replace tags with what your chart version uses)
docker pull localhost:15001/astronomer/ap-houston:latest
docker pull localhost:15001/astronomer/ap-commander:latest

# Warm the elastic cache
docker pull localhost:15003/elasticsearch/elasticsearch:8.18.6
```

---

## Persistent State

| Resource | Lifecycle |
|---|---|
| Registry containers | Persist across k3d cluster destroy/recreate. Survive Docker daemon restarts (`--restart always`). |
| Cache volumes (`astronomer-registry-proxy-*-data`) | Persist until `--destroy --purge` is run or volumes are manually removed. |
| k3d registry config (`~/.local/share/astronomer-software/k3d-registry.yaml`) | Regenerated on every script run. |
| Per-registry Docker configs (`~/.local/share/astronomer-software/registry-configs/`) | Regenerated on every script run. |

---

## Troubleshooting

### Images still pulling slowly after setup

Check that the registry containers are running and attached to the correct network:

```bash
python3 bin/setup-local-registry.py --status
docker network inspect astronomer-net | grep -A3 "astronomer-registry"
```

If a container is missing from the network, remove and re-run:

```bash
python3 bin/setup-local-registry.py --destroy
python3 bin/setup-local-registry.py
```

### `Too Many Requests` from quay.io or docker.io

The proxy is not being used. Verify:
1. The registry containers are running (`python3 bin/setup-local-registry.py --status`)
2. The cluster was created with `--registry-config` (check for the milestone step in script output)
3. The containers are on the same Docker network as the k3d nodes

### Cache is stale or corrupted

Purge all cached data and let the proxies repopulate on the next cluster spin-up:

```bash
python3 bin/setup-local-registry.py --destroy --purge
python3 bin/setup-local-registry.py
```

### `registry:2` image itself needs pulling

The first time you run the setup, Docker must pull the `registry:2` image from Docker Hub. This is a one-time ~30 MB pull. Subsequent runs use the locally cached Docker image.

### Containers not reachable from k3d nodes

The `--registry-config` flag must be passed at **cluster creation time** — it cannot be applied to an existing cluster. If you added the local registry after creating a cluster, recreate the cluster:

```bash
# For setup-037x-k3d.py
python3 bin/setup-037x-k3d.py --recreate-cluster

# For setup-cp-dp-k3d.py
python3 bin/setup-cp-dp-k3d.py --recreate-clusters
```
