# Adopting the Astro Runtime Operator itself, and transitioning off a customer-run operator

> **Status: internal draft. Design input and hazard analysis, not a runbook.**
> Nothing here has been validated on a cluster. The candidate procedure below is a sketch with a
> known-destructive failure mode; do not hand any part of it to a customer until the open questions
> are closed and the steps have been exercised end to end. See "What would make this publishable".

## Why this doc exists

Two review comments on the customer-facing adoption page asked for this, both from Ian Buss:

> We don't actually do this - the operator deployment is left alone in this model IIUC. We should
> separately document "adoption" of the operator itself.

> We will want a transition doc so the customer doesn't have to continue owning and operating the
> operator outside of APC.

They read as two asks but they are one underlying change: moving the operator from
customer-installed-and-operated to APC-installed-and-operated. This doc covers what that change
involves, what it would break today, and what is still undecided.

Related: Ian also raised a "full adoption" plan in the adoption Slack thread, which is the same
theme reached from the failover angle (adopted deployments are not covered by data-plane failover
because their definition lives in a custom resource APC did not create).

## What adoption does and does not cover today

Deployment adoption adopts **Airflow deployments**, one custom resource each. It does not touch the
operator. Concretely, on a data plane whose cluster already runs the operator, the documented
configuration is:

```yaml
global:
  airflowOperator:
    enabled: true          # Houston and Commander are operator-aware
    adoption:
      enabled: true

airflow-operator:
  enabled: false           # do NOT install APC's own operator; the cluster already has one
```

So after adoption the split of responsibility is:

| Who | Owns |
| --- | --- |
| APC | The adopted Airflow deployments, to the extent listed in the adoption page's ownership table |
| The customer | Installing, upgrading, configuring and monitoring the operator itself, plus its CRDs, RBAC and webhooks |

The customer therefore still runs a piece of Astronomer infrastructure out-of-band, which is
exactly Ian's objection. Nothing about deployment adoption changes that, and nothing in the
platform currently moves it.

## What "adopting the operator" would mean

Flipping `airflow-operator.enabled` to `true` so the umbrella chart installs and owns the operator,
and removing the customer's standalone installation. That is the whole idea, and it is deceptively
small: the two installations are not interchangeable, and the switch is not a Helm value flip.

### The two installations differ in ways that matter

The umbrella subchart (`astronomer/charts/airflow-operator`) names its namespaced resources after
the release:

| Resource | Umbrella subchart | Standalone chart (`airflow-operator/helm`) |
| --- | --- | --- |
| Manager Deployment | `<release>-aocm` | `airflow-operator-controller-manager` |
| Webhook Service | `<release>-airflow-operator-webhook-service` | `airflow-operator-webhook-service` |
| Mutating webhook config | `<release>-airflow-operator-mutating-webhook-configuration` | `airflow-operator-mutating-webhook-configuration` |
| Validating webhook config | `<release>-airflow-operator-validating-webhook-configuration` | `airflow-operator-validating-webhook-configuration` |
| Manager ConfigMap | `<release>-aom-config` | `airflow-operator-manager-config` |
| CRDs | `airflows.airflow.apache.org` and siblings, **with `helm.sh/resource-policy: keep`** | the same names, **without any resource policy**, gated on `crd.create` (default `true`) |

Two consequences fall straight out of that table.

**Namespaced resources do not collide.** Different names, so both operators can be installed at the
same time without Helm complaining. That is a runtime hazard rather than a safeguard, see below.

**The CRDs do collide**, because CRDs are cluster-scoped with fixed names. They are also the
difference that makes the transition dangerous.

## Hazards, worst first

### 1. Uninstalling the standalone operator can destroy every Airflow deployment on the cluster

The standalone chart renders its CRDs as ordinary templates with `crd.create: true` by default and
**no `helm.sh/resource-policy: keep`**. So `helm uninstall` of that release deletes the CRDs. Deleting
a CRD cascades to every custom resource of that kind, which means every Airflow deployment on the
cluster, adopted or not.

This matters more than any other item here because "uninstall the standalone operator, then enable
the bundled one" is the obvious first instinct for this transition, and it is catastrophic.

The umbrella subchart does carry `resource-policy: keep`, so the hazard is asymmetric: uninstalling
APC's operator is survivable, uninstalling the customer's is not.

### 2. Helm will refuse to adopt the existing CRDs

The subchart ships the CRDs as templates, so enabling it on a cluster where those CRDs already
exist under another Helm release fails the upgrade with an ownership error along the lines of
`invalid ownership metadata; annotation validation error: key "meta.helm.sh/release-name" must equal ...`.

The transition therefore has to deal with CRD ownership explicitly. Candidate approaches, none
tested:

- Re-label and re-annotate the existing CRDs to the astronomer release
  (`meta.helm.sh/release-name`, `meta.helm.sh/release-namespace`, `app.kubernetes.io/managed-by`)
  before enabling the subchart.
- Set `crd.create: false` on the standalone release first so it stops claiming them, then decide
  whether that leaves them unowned in a way Helm will accept.
- Leave the CRDs owned by the customer's release permanently and never enable the subchart's CRD
  templates, which needs a subchart option that does not exist today.

### 3. Two operators reconciling the same resources

Because the namespaced resources do not collide, a partially completed transition leaves two
managers running. Both watch the same custom resources, and both register a mutating webhook, so
every write to an Airflow resource is defaulted twice by two possibly different operator versions,
and two controllers reconcile the same sub-resources. This is not a supported configuration and the
failure modes have not been characterised.

The standalone chart has an `airflowNamespaces` value that scopes the operator to a namespace list,
which is the obvious lever for a phased, namespace-by-namespace migration rather than a cutover.
Whether the umbrella subchart can be scoped the same way needs checking.

### 4. Version skew

The customer's operator version and the version the umbrella chart pins are independent today. A
transition changes the running operator version at the same time as changing who owns it, which
couples an ownership change to a functional upgrade. Those are worth separating.

## A candidate transition, unvalidated

Recording the shape of it so the open questions have something to attach to. **Do not follow this.**

1. Inventory: operator version, whether `crd.create` was true, which namespaces it watches, and
   every Airflow custom resource on the cluster.
2. Stop the standalone manager without uninstalling its release, for example by scaling
   `airflow-operator-controller-manager` to zero, so nothing reconciles during the switch.
3. Resolve CRD ownership by one of the approaches in hazard 2.
4. Enable `airflow-operator.enabled: true` and upgrade the platform release.
5. Remove the standalone release in a way that cannot delete CRDs, which means confirming
   `crd.create: false` or removing the CRDs from that release's manifest first.
6. Verify: one manager running, one mutating and one validating webhook configuration serving,
   every Airflow resource still present, and a reconcile actually happening.

Every one of those steps needs the "what if it fails halfway" answer written down before this is
usable, because the halfway states include "no operator is reconciling anything".

## Open questions

- Is this a product commitment or a support-assisted migration? The answer decides whether the
  output is a customer doc or an internal runbook.
- Can the subchart install without its CRD templates, so CRD ownership can stay where it is?
- Can the umbrella subchart be namespace-scoped like the standalone chart's `airflowNamespaces`,
  which would allow phased migration instead of cutover?
- Should the standalone chart gain `helm.sh/resource-policy: keep` on its CRDs regardless of this
  work? It looks like a latent footgun independent of any transition, and it is a one-line change.
- What is the rollback? Once CRD ownership moves to the astronomer release, moving it back is the
  same problem in reverse.
- Does any of this need to happen before adopted deployments can be covered by data-plane failover,
  or are those independent?

## What would make this publishable

1. A decision on the first open question, since it sets the audience.
2. The CRD ownership approach chosen and exercised on a cluster with real Airflow deployments,
   including a deliberate mid-transition failure.
3. `helm.sh/resource-policy: keep` on the standalone chart's CRDs, or a documented reason not to.
4. A verification procedure that proves exactly one operator is live and reconciling.
5. Automation coverage, most naturally alongside the adoption tests in
   `software-upgrade-automation/tests/cpdp/operator_adoption/`.

Until then the customer-facing adoption page stays as it is: it documents that the cluster's
existing operator is left alone, and says nothing about moving it.
