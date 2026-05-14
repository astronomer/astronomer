# APC Architecture

This document describes the architecture of the Astro Private Cloud (APC) platform across its installation modes. It is reference material for engineers working on the chart, operators deploying it, and AI agents acting on the codebase.

## Overview

APC is delivered as a single umbrella Helm chart in this repository. One Helm release installs the **platform** — the control surface (Houston, Astro UI, Commander), the image registry, the logging stack (Elasticsearch + Vector), the metrics stack (Prometheus, Alertmanager, Grafana), and the supporting infrastructure (NATS, ingress) — into a Kubernetes cluster. Once installed, the platform itself provisions user **Airflow deployments** on demand: each deployment is a separate Helm release (using `astronomer/airflow-chart`) that the platform's Commander service creates and manages in its own namespace.

The single chart can be installed in three modes, controlled by `global.plane.mode` in `values.yaml`:

| Mode | What it installs | When to use |
|------|------------------|-------------|
| `unified` (default) | Control Plane and Data Plane components co-located in one cluster | Local development, single-cluster deployments, the v0.x compatibility shape |
| `control` | Control Plane only | Multi-cluster deployments where one CP manages one or more remote DPs |
| `data` | Data Plane only, identified by `global.plane.domainPrefix` (e.g. `dp01`) | Each DP cluster attached to a remote CP |

### Why the modes exist

The CP/DP split is an infrastructure separation of concerns. It lets operators scale the Data Plane horizontally without touching the Control Plane, and lets a single CP manage Data Planes that live in heterogeneous environments — for example one DP in Azure ARO, another in GCP, and another on-prem alongside physical devices. Unified mode is used primarily as a migration path from older versions that did not have a CP/DP split, and is not recommended for new installations.

## Component inventory

The table below lists components installed by this chart and the modes in which each one renders. "Gate" names the values that control the component beyond mode. Components grouped together are governed by a single tag in `Chart.yaml` (e.g. `monitoring`, `logging`, `platform`); disabling the tag disables the group.

### Control-plane components

These render when `global.plane.mode` is `control` or `unified`.

| Component | Role | Gate |
|-----------|------|------|
| Houston API | GraphQL/REST API; source of truth for users, workspaces, and deployments | `global.astronomer.enabled` |
| Houston worker | Async job processor; invokes Commander to create/update Airflow deployments | `global.astronomer.enabled` |
| Astro UI | Web UI for the platform | `global.astronomer.enabled` |
| Navigator | Multi-DP coordinator (used for DP failover) | `navigator.enabled` or `global.dataPlaneFailover.enabled` |
| dp-link | CP-side endpoint for DP-link traffic (DP failover path) | `dpLink.enabled` or `global.dataPlaneFailover.enabled` |
| nginx (CP variant) | Ingress for CP hostnames at `<baseDomain>` | `global.nginx.enabled` |
| Alertmanager | Alert routing for platform Prometheus | `global.alertmanager.enabled` |
| Grafana | Dashboards backed by CP Prometheus | `global.grafana.enabled` |

### Data-plane components

These render when `global.plane.mode` is `data` or `unified`.

| Component | Role | Gate |
|-----------|------|------|
| Commander | gRPC service that runs `helm install/upgrade` per user Airflow deployment | `global.astronomer.enabled` |
| Registry | Docker registry for user-built Airflow images | `global.astronomer.enabled` |
| Pilot | DP-side health/failover agent | `pilot.enabled` or `global.dataPlaneFailover.enabled` |
| config-syncer | CronJob that pulls Houston configuration into the local cluster | `configSyncer.enabled` |
| nginx (DP variant) | Ingress for DP hostnames at `<domainPrefix>.<baseDomain>` | `global.nginx.enabled` |
| Prometheus federation proxy | Auth-protected `/federate` endpoint that CP Prometheus scrapes | rendered only when `mode=data` |
| external-es-proxy | Forwards logs to an external Elasticsearch | `global.customLogging.enabled` |

### Plane-agnostic infrastructure

These render in every mode (subject to their own enable flag) and run independently in each cluster.

| Component | Role | Gate |
|-----------|------|------|
| Prometheus | Metrics collection (per-plane instance) | `global.prometheus.enabled` |
| Elasticsearch | Log storage | `global.elasticsearch.enabled` |
| Vector | Daemonset log collector | `global.daemonsetLogging.enabled` |
| NATS | Local message bus (one cluster per plane; not federated by default) | `global.nats.enabled` |
| kube-state | Kubernetes object metrics | `global.kubeState.enabled` |
| PostgreSQL | In-cluster database for dev/test (production should use external) | `global.postgresql.enabled` |
| PgBouncer | Connection pooling in front of Postgres | `global.pgbouncer.enabled` |
| prometheus-postgres-exporter | Database metrics | `global.prometheusPostgresExporter.enabled` |
| airflow-operator | Optional CRD-based Airflow management | `global.airflowOperator.enabled` |
| external-secrets (ESO) | Secret synchronization | `external-secrets.enabled` |

`Chart.yaml` is the canonical source for conditions and tags; `values.yaml` is the canonical source for `global.plane.*` defaults.

## How user Airflow deployments fit in

The platform installed by this chart is the *runtime* that creates Airflow. Each user-facing Airflow deployment is a separate Helm release living alongside the platform release in the same DP cluster:

1. A user creates a deployment via the Astro UI or Houston API.
2. Houston persists the deployment definition in its database.
3. The Houston worker emits a job that calls Commander over gRPC.
4. Commander runs `helm install` (or `helm upgrade`) using the chart referenced by `astronomer.houston.config.deployments.helm.airflow` — the external `astronomer/airflow-chart` — into a dedicated namespace.
5. The new Airflow release runs alongside (but independently of) the APC platform release.

This is why a healthy DP cluster contains **one APC Helm release plus N Airflow Helm releases**, one per user deployment. The chart's RBAC (`charts/astronomer/templates/commander/commander-role.yaml`), network policies, and registry are sized to accommodate many sibling Airflow releases that this chart never templates directly.

## Cross-plane communication

In `control` + `data` deployments, the two planes are wired together through ingress on each side and a small set of shared secrets. All wires assume the CP is reachable at `<baseDomain>` and each DP at `<domainPrefix>.<baseDomain>`.

### CP → DP

| Wire | Purpose |
|------|---------|
| Houston worker → `commander.<domainPrefix>.<baseDomain>:9091` (gRPC) | Drives Airflow deployment lifecycle on the DP |
| Houston/UI → Commander metadata HTTP ingress | Reads DP-side cluster and deployment state |
| CP Prometheus → `prometheus.<domainPrefix>.<baseDomain>/federate` | Aggregates DP metrics into platform dashboards |

### DP → CP

| Wire | Purpose |
|------|---------|
| Kubelet/containerd in DP → `houston.<baseDomain>/v1/registry/authorization` | Authorizes image pulls from the DP registry |
| config-syncer (DP) → Houston HTTPS | Pulls platform configuration into the DP cluster |

### Shared trust and auth

- **Shared registry auth token.** `global.authHeaderSecretName` references the same Secret on both planes. It signs registry-authorization round-trips and authenticates Prometheus federation.
- **TLS certificate.** `global.tlsSecret` (default `astronomer-tls`) must cover both `<baseDomain>` (and its subdomains) and each `<domainPrefix>.<baseDomain>` it serves. The k3d setup script generates a cert with SANs for all of these.
- **Private CA trust.** `global.privateCaCerts` is a list of Secret names containing CA bundles; pods mount them at `/usr/local/share/ca-certificates/` and run `update-ca-certificates` on start (controlled via `UPDATE_CA_CERTS`). `global.privateCaCertsAddToHost` extends the trust to the node so kubelet/containerd can pull from registries signed by the same CA.
- **Cluster-local service auth.** `global.clusterLocalServiceAuth.token` is auto-generated and shared between intra-plane services (e.g. Pilot ↔ Commander) for gRPC authentication.

### NATS

NATS runs locally inside each plane (one cluster per plane) and is **not federated** by default. The `leafnode` and `gateway` configuration knobs in `charts/nats/values.yaml` exist for environments that want to bridge planes, but the stock chart ships them disabled.

## Topology

### Unified mode

```mermaid
flowchart TB
    subgraph cluster["Single cluster (mode=unified)"]
        direction TB
        subgraph cp_components["Control-plane components"]
            houston["Houston API + worker"]
            ui["Astro UI"]
            alertmanager["Alertmanager"]
            grafana["Grafana"]
        end
        subgraph dp_components["Data-plane components"]
            commander["Commander"]
            registry["Registry"]
        end
        subgraph shared["Plane-agnostic"]
            prom["Prometheus"]
            es["Elasticsearch"]
            vector["Vector"]
            nats["NATS"]
        end
        nginx["nginx → &lt;baseDomain&gt;"]
        airflow["N × Airflow Helm releases<br/>(one per user deployment)"]
    end
```

### Split mode (control + data)

```mermaid
flowchart LR
    subgraph cp["CP cluster (mode=control) → &lt;baseDomain&gt;"]
        direction TB
        cp_houston["Houston (API + worker)"]
        cp_ui["Astro UI"]
        cp_link["Navigator · dp-link"]
        cp_alerts["Alertmanager · Grafana"]
        cp_prom["Prometheus (CP)"]
        cp_shared["Elasticsearch · Vector · NATS<br/>kube-state · postgres/pgbouncer"]
        cp_nginx["nginx (CP)"]
    end
    subgraph dp["DP cluster (mode=data, domainPrefix=dp01) → dp01.&lt;baseDomain&gt;"]
        direction TB
        dp_cmd["Commander"]
        dp_reg["Registry"]
        dp_pilot["Pilot · config-syncer"]
        dp_prom["Prometheus (DP)<br/>+ federation-auth proxy"]
        dp_shared["Elasticsearch · Vector · NATS<br/>kube-state · postgres/pgbouncer"]
        dp_nginx["nginx (DP)"]
        dp_airflow["N × Airflow Helm releases"]
    end
    cp_houston -- "gRPC<br/>commander.dp01.&lt;baseDomain&gt;:9091" --> dp_cmd
    cp_prom -- "scrape /federate" --> dp_prom
    dp_reg -- "registry/authorization" --> cp_houston
    dp_pilot -- "config sync (HTTPS)" --> cp_houston
```

### Multiple Data Planes

One CP can serve N Data Planes. Each DP installs the chart with a unique `global.plane.domainPrefix` (e.g. `dp01`, `dp02`, …) and a TLS cert that covers its prefix.

```mermaid
flowchart TB
    cp["CP cluster<br/>&lt;baseDomain&gt;"]
    dp1["DP cluster · dp01.&lt;baseDomain&gt;<br/>(e.g. Azure ARO)"]
    dp2["DP cluster · dp02.&lt;baseDomain&gt;<br/>(e.g. GCP)"]
    dp3["DP cluster · dp03.&lt;baseDomain&gt;<br/>(e.g. on-prem with physical devices)"]
    cp --- dp1
    cp --- dp2
    cp --- dp3
```

## Where to look next

- [`Chart.yaml`](../Chart.yaml) — canonical list of sub-charts with their `condition` and `tags`.
- [`values.yaml`](../values.yaml) — `global.plane.*`, `global.tlsSecret`, `global.authHeaderSecretName`, `global.privateCaCerts`, and the `*.enabled` flags referenced above.
- [`docs/cp-dp-k3d-setup-guide.md`](cp-dp-k3d-setup-guide.md) — working example of a split deployment on k3d, with the CoreDNS and TLS wiring spelled out.
- [`docs/local-development.md`](local-development.md) — quick-start for chart development and local clusters.
- `astronomer/airflow-chart` repo — the chart that Commander instantiates per user deployment.
