# Adopting the Astro Runtime Operator itself, and transitioning off a customer-run operator

> **Status: internal draft. Not yet exercised on a cluster.**
> The sequence below is grounded in the two charts rather than in a tested migration, so treat steps
> 3 to 5 as unvalidated. **Step 1 is different**: it is a metadata-only change that closes a
> data-loss hazard, it is safe to apply today, and it should be applied whether or not a customer
> ever moves to a managed operator. See "What would make this publishable".

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

### 1. Uninstalling the standalone operator destroys every Airflow deployment on the cluster

The standalone chart renders its CRDs as ordinary templates with `crd.create: true` by default and
**no `helm.sh/resource-policy: keep`** (confirmed absent from the entire history of that chart, not
just current `main`). So `helm uninstall` of that release deletes the CRDs, and deleting a CRD
cascades to every custom resource of that kind: every Airflow deployment on the cluster, adopted or
not.

This ranks first because "uninstall the standalone operator, then enable the bundled one" is the
obvious first instinct for this transition.

**The fix is one command, and it is worth applying immediately, transition or not:**

```bash
kubectl get crd -o name | grep airflow.apache.org \
  | xargs kubectl annotate --overwrite helm.sh/resource-policy=keep
```

Helm honours that annotation both when an upgrade would remove the resource and when an uninstall
would delete it, so after this no Helm command against the operator release can take the CRDs with
it. It changes metadata only and has no effect on anything running.

The umbrella subchart already carries the annotation on all 13 of its CRDs, so the exposure is
asymmetric: uninstalling APC's operator is survivable, uninstalling an un-annotated standalone one
is not.

### 2. Stopping the old manager on its own blocks every write to an Airflow resource

Both charts set `failurePolicy: Fail` on the mutating webhook. So if the manager is scaled to zero
while its webhook configuration still exists, the API server has no backend to admit CR writes and
rejects all of them, including APC's applies and any `kubectl edit`.

This inverts the intuitive order. "Stop the old operator first, then switch" is precisely the wrong
move. The manager and its webhook configuration have to go together, which is what `helm uninstall`
does for the standalone release.

Already-running Airflow is unaffected either way: the webhook gates writes to the custom resource,
not the pods that already exist.

### 3. Helm will not adopt the existing CRDs by default

The subchart ships the CRDs as templates, so enabling it where those CRDs already belong to another
Helm release fails with `invalid ownership metadata; annotation validation error: key
"meta.helm.sh/release-name" must equal ...`.

There are two ways through, because **the umbrella subchart also exposes `crd.create`**
(`charts/airflow-operator/values.yaml:8`, default `true`):

- **Leave the CRDs unmanaged.** Install with `airflow-operator.crd.create: false`. Nothing contends
  for ownership. The cost is that CRD schema changes become a manual `kubectl apply` whenever an
  operator upgrade needs them.
- **Transfer ownership to the platform release.** Set `meta.helm.sh/release-name`,
  `meta.helm.sh/release-namespace` and `app.kubernetes.io/managed-by=Helm` on the CRDs, and leave
  `crd.create: true`. CRD updates then flow with the platform chart and inherit its
  `resource-policy: keep`. Cleaner long-term, one more step to get wrong.

### 4. This is a cutover, not a phased migration

The standalone chart has `airflowNamespaces` for scoping the operator to a namespace list. The
umbrella subchart does **not**, and the webhooks carry no `namespaceSelector`. So there is no
supported way to migrate namespace by namespace: every Airflow resource on the cluster changes
operator at the same moment.

### 5. Two operators reconciling the same resources

Because the namespaced resources are named differently, both operators can be installed at once
without Helm objecting. Both then watch the same custom resources and both register a mutating
webhook, so every write is defaulted twice by two possibly different versions while two controllers
reconcile the same sub-resources. Not a supported configuration, and the failure modes are
uncharacterised. The sequence below avoids the state entirely.

### 6. Version skew

The customer's operator version and the version the umbrella chart pins are independent today, so a
transition changes the running operator version at the same time as changing who owns it. Worth
separating: land the ownership change on the version they already run where possible.

### 7. CRD CA injection is name and namespace sensitive

The umbrella subchart's 13 CRDs annotate
`cert-manager.io/inject-ca-from: <namespace>/airflow-operator-serving-cert`, but the Certificate the
chart creates is `<release>-airflow-operator-serving-cert`. The names do not match, so cert-manager
cannot populate the CA on the CRD conversion webhook. Its own webhook configurations get this right
and use the release-prefixed name.

Latent today, because the CRD serves a single version so conversion never fires. It becomes real the
day a second API version is introduced. The same shape of problem applies to standalone-created CRDs
kept across a namespace move, since the annotation names a namespace that may no longer hold a
Certificate.

## The transition sequence

Grounded in both charts; steps 3 to 5 have not been exercised on a cluster.

1. **Protect the CRDs.** Apply the annotation from hazard 1. Safe today, independent of everything
   else.
2. **Cordon the adopted deployments.** Stops APC writing to any custom resource during the window,
   which is what makes the gap in step 3 harmless.
3. **`helm uninstall` the standalone operator release.** Manager and webhook configuration go
   together, so there is never an orphaned webhook rejecting writes. The CRDs survive because of
   step 1, and running Airflow keeps running because its workloads are ordinary Deployments and
   StatefulSets that Kubernetes maintains without the operator.
4. **Choose CRD ownership** using one of the two options in hazard 3.
5. **Set `airflow-operator.enabled: true`** and upgrade the platform release.
6. **Verify:** exactly one manager, one mutating and one validating webhook configuration, every
   Airflow custom resource still present, and a reconcile actually happening.
7. **Uncordon**, then trigger a deployment update so APC re-applies and the new operator reconciles.

Uninstalling before installing, rather than overlapping the two operators, is deliberate. An overlap
means two mutating webhooks defaulting the same resource and two controllers reconciling the same
sub-resources at possibly different versions. A brief no-operator gap has nothing fighting in it,
and its only real cost, CR writes landing undefaulted, is what the cordon in step 2 removes.

## Open questions

Answered while writing this, recorded so they are not re-investigated:

- ~~Can the subchart install without its CRD templates?~~ Yes, `airflow-operator.crd.create: false`.
- ~~Can the umbrella subchart be namespace-scoped like `airflowNamespaces`?~~ No. Cutover only.
- ~~Should the standalone chart gain `helm.sh/resource-policy: keep`?~~ Yes, and it is filed as its
  own bug: it endangers any customer who uninstalls their operator release, with or without this
  work.

Still open:

- Is this a product commitment or a support-assisted migration? The answer decides whether the
  output is a customer doc or an internal runbook, and it is the only question blocking that call.
- What is the rollback once CRD ownership has moved to the platform release? The same problem in
  reverse, and it needs an answer before this is customer-facing.
- How long is the no-operator gap in practice, and is a cordon sufficient protection for it, or does
  the platform need to refuse applies while no operator is present?
- Does any of this need to happen before adopted deployments can be covered by data-plane failover,
  or are those independent?

## What would make this publishable

1. A decision on the first open question, since it sets the audience.
2. Steps 3 to 5 exercised on a cluster with real Airflow deployments, including a deliberate
   mid-transition failure to establish the recovery path.
3. `helm.sh/resource-policy: keep` shipped on the standalone chart's CRDs, so step 1 becomes the
   default rather than a prerequisite the customer has to be told about.
4. A verification procedure that proves exactly one operator is live and reconciling.
5. Automation coverage, most naturally alongside the adoption tests in
   `software-upgrade-automation/tests/cpdp/operator_adoption/`.

Until then the customer-facing adoption page stays as it is: it documents that the cluster's
existing operator is left alone, and says nothing about moving it.
