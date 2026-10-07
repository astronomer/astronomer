{{- define "logging.indexNamePrefix" -}}
{{- if .Values.global.logging.indexNamePrefix -}}
{{- .Values.global.logging.indexNamePrefix -}}
{{- else -}}
{{- if .Values.global.logging.loggingSidecar.enabled  -}}
vector
{{- else -}}
fluentd
{{- end -}}
{{- end -}}
{{- end -}}


{{/*
Base domain for the control-plane auth flow (auth-url / auth-signin subrequests and
redirects, elasticsearch proxy_pass). Under control-plane HA the customer enters via the
global hostname and the session cookie is scoped to globalBaseDomain, so these auth URLs
must resolve to the global host. Falls back to baseDomain when HA is off (single-CP
rendering unchanged) or when globalBaseDomain is unset (e.g. data planes, where it is
never templated). Consumers template the surrounding URL/key, so this is reusable for any
auth-flow URL regardless of annotation key.
*/}}
{{- define "global.authBaseDomain" -}}
{{- if and .Values.global.controlPlaneHA.enabled .Values.global.controlPlaneHA.globalBaseDomain -}}
{{- .Values.global.controlPlaneHA.globalBaseDomain -}}
{{- else -}}
{{- .Values.global.baseDomain -}}
{{- end -}}
{{- end -}}

{{ define "houston.internalauthurl" -}}
{{- if eq (include "astronomer.controlPlaneEnabled" .) "true" }}
nginx.ingress.kubernetes.io/auth-url: http://{{ .Release.Name }}-houston.{{ .Release.Namespace }}.svc.cluster.local:8871/v1/authorization
{{- else }}
nginx.ingress.kubernetes.io/auth-url: https://houston.{{ include "global.authBaseDomain" . }}/v1/authorization
{{- end }}
{{- end }}


{{/*
DEPRECATED: containerd.configToml is retained as an escape hatch for operators who need
to supply fully custom TOML/hosts.toml content via containerdConfigToml.
For containerd 2.x (GKE 1.33+), the daemonset script auto-generates a correct hosts.toml
when containerdConfigToml is not set (nil). Prefer using containerdVersion: "2" instead.
*/}}
{{ define "containerd.configToml" -}}
{{- .Values.global.privateCaCertsAddToHost.containerdConfigToml -}}
{{- end }}

{{/*
Registry hostname differs between unified and data-plane installs
because data-plane clusters prefix the base domain with
`global.plane.domainPrefix`.
*/}}
{{- define "containerd.registryHost" -}}
{{- if eq .Values.global.plane.mode "data" -}}
registry.{{ .Values.global.plane.domainPrefix }}.{{ .Values.global.baseDomain }}
{{- else -}}
registry.{{ .Values.global.baseDomain }}
{{- end -}}
{{- end }}

{{ define "dagOnlyDeployment.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-dag-deploy:{{ .Values.global.deployMechanisms.dagOnlyDeployment.tag }}
{{- else -}}
{{ .Values.global.deployMechanisms.dagOnlyDeployment.repository }}:{{ .Values.global.deployMechanisms.dagOnlyDeployment.tag }}
{{- end }}
{{- end }}

{{ define "authSidecar.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-auth-sidecar:{{ .Values.global.authSidecar.tag }}
{{- else -}}
{{ .Values.global.authSidecar.repository }}:{{ .Values.global.authSidecar.tag }}
{{- end }}
{{- end }}

{{/*
Render a container-level securityContext for PSS-Restricted conformance.

Call with a list of two elements: (list $ $override) where
  - $        is the current context (so the helper can read .Values.securityContext and .Values.global)
  - $override is a per-container securityContext map (or nil). Its fields are layered on top of the
    chart's .Values.securityContext, so a container that only differs by runAsUser can pass
    (dict "runAsUser" 101) and inherit every other field from the chart default.

Behavior:
  - readOnlyRootFilesystem is always force-merged to true (customers cannot disable it).
  - Every other field is a default (override layered over .Values.securityContext), so it remains
    overridable via helm values.
  - runAsUser is omitted on OpenShift so the cluster's SCC can assign a UID from its allowed range.
    This matches the prometheus/elasticsearch helpers as of PINF-765.
  - runAsUser is also omitted when it is set to the string "auto", an escape hatch that lets the
    platform (or a user) defer UID assignment off OpenShift too. Rendering "runAsUser: auto" is never
    valid, so omitting it is always correct.
*/}}
{{- define "platform.containerSecurityContext" -}}
{{- $ctx := index . 0 -}}
{{- $override := index . 1 | default dict -}}
{{- $required := dict "readOnlyRootFilesystem" true -}}
{{- $base := merge (deepCopy $override) $ctx.Values.securityContext -}}
{{- if or $ctx.Values.global.openshift.enabled (eq (toString $base.runAsUser) "auto") -}}
{{- merge $required (omit $base "runAsUser") | toYaml -}}
{{- else -}}
{{- merge $required $base | toYaml -}}
{{- end -}}
{{- end }}

{{/*
Render a pod-level securityContext.

Call with a list of two elements: (list $ $override) where
  - $        is the current context (so the helper can read .Values.podSecurityContext and .Values.global)
  - $override is a per-pod podSecurityContext map (or nil). Its fields are layered on top of the
    chart's .Values.podSecurityContext.

Behavior:
  - fsGroup, runAsGroup and runAsUser are omitted on OpenShift, where the cluster's SCC assigns
    them from its allowed range. Every other field (e.g. seccompProfile) is preserved.
  - Off OpenShift the merged podSecurityContext is rendered unchanged.
This is the pod-level counterpart of platform.containerSecurityContext.
*/}}
{{- define "platform.podSecurityContext" -}}
{{- $ctx := index . 0 -}}
{{- $override := index . 1 | default dict -}}
{{- $base := merge (deepCopy $override) $ctx.Values.podSecurityContext -}}
{{- if $ctx.Values.global.openshift.enabled -}}
{{- omit $base "fsGroup" "runAsGroup" "runAsUser" | toYaml -}}
{{- else -}}
{{- toYaml $base -}}
{{- end -}}
{{- end }}

{{ define "loggingSidecar.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-vector:{{ .Values.global.logging.loggingSidecar.tag }}
{{- else -}}
{{ .Values.global.logging.loggingSidecar.repository }}:{{ .Values.global.logging.loggingSidecar.tag }}
{{- end }}
{{- end }}

{{ define "certCopier.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-db-bootstrapper:{{ .Values.global.privateCaCertsAddToHost.certCopier.tag }}
{{- else -}}
{{ .Values.global.privateCaCertsAddToHost.certCopier.repository }}:{{ .Values.global.privateCaCertsAddToHost.certCopier.tag }}
{{- end }}
{{- end }}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "certCopier.imagePullSecrets" -}}
{{- if and .Values.global.privateRegistry.enabled .Values.global.privateRegistry.secretName }}
imagePullSecrets:
  - name: {{ .Values.global.privateRegistry.secretName }}
{{- end -}}
{{- end -}}

{{- define "global.podLabels" -}}
{{- if .Values.global.podLabels }}
{{- toYaml .Values.global.podLabels }}
{{- end }}
{{- end }}

{{- define "houston-proxy" -}}
{{- if eq .Values.global.plane.mode "unified" -}}
proxy_pass http://{{ .Release.Name }}-houston.{{ .Release.Namespace }}:8871/v1/elasticsearch;
{{- else -}}
proxy_pass https://houston.{{ include "global.authBaseDomain" . }}/v1/elasticsearch;
{{- end -}}
{{- end }}

{{ define "registry.authHeaderSecret" -}}
{{ default (printf "%s-registry-auth-key" .Release.Name) .Values.global.authHeaderSecretName }}
{{- end }}

{{/*
Whether the logging stack (Elasticsearch, external-es-proxy, Vector) should be rendered
for the current plane. Always on for unified. When global.sharedElasticsearch.enabled,
the control plane hosts shared logging and the data plane runs none; when disabled, the
data plane runs its own and the control plane runs none.
Defined in the parent chart so all logging sub-charts can include it.
Returns the string "true" or "false" — compare with eq.
*/}}
{{- define "logging.enabled" -}}
{{- or (eq .Values.global.plane.mode "unified") (and (eq .Values.global.plane.mode "control") .Values.global.sharedElasticsearch.enabled) (and (eq .Values.global.plane.mode "data") (not .Values.global.sharedElasticsearch.enabled)) -}}
{{- end }}

{{/*
Master switch for all platform Ingress objects. Defaults to enabled so upgrades are a no-op;
set global.ingress.enabled: false to suppress every Ingress. Defaults to true only when the
key is absent (not via `default`, which treats a boolean false as empty).
Defined in the parent chart so all sub-charts can include it.
Returns the string "true" or "false" — compare with eq.
*/}}
{{- define "global.ingress.enabled" -}}
{{- if hasKey (.Values.global.ingress | default dict) "enabled" -}}
{{- .Values.global.ingress.enabled -}}
{{- else -}}
true
{{- end -}}
{{- end }}

{{- /*
CP-HA: the control-plane base domain a data plane targets for control-plane services (Houston).
Under Control Plane HA this is the GLOBAL base domain so DP->CP requests health-route to whichever
control plane is active as pinning to a single CP's per-CP baseDomain breaks DP->CP calls after a
CP/region failover (if the pinned CP is the one that is down).
When HA is enabled, globalBaseDomain is REQUIRED on every plane, so the HA branch always resolves. The
per-CP fallback below is reached only when HA is disabled. Only meaningful on data planes.
*/ -}}
{{- define "houston.controlPlaneBaseDomain" -}}
{{- if and .Values.global.controlPlaneHA.enabled .Values.global.controlPlaneHA.globalBaseDomain -}}
{{- .Values.global.controlPlaneHA.globalBaseDomain -}}
{{- else -}}
{{- .Values.global.baseDomain -}}
{{- end -}}
{{- end -}}

{{- /*
Common Helper template for control or unified mode
*/ -}}
{{- define "astronomer.controlPlaneEnabled" -}}
{{- if or (eq .Values.global.plane.mode "control") (eq .Values.global.plane.mode "unified") -}}
true
{{- end -}}
{{- end -}}

{{- /*
The namespace KEDA resolves cluster-scoped TriggerAuthentication objects in: its
KEDA_CLUSTER_OBJECT_NAMESPACE, which defaults to the namespace KEDA runs in.
*/ -}}
{{- define "keda.clusterObjectNamespace" -}}
{{- default .Values.global.keda.namespace .Values.global.keda.clusterObjectNamespace -}}
{{- end -}}

{{- /*
Name of the scaling identity and the cluster-scoped authentication object naming it.
A deployment's scaling trigger references this name, so it is fixed rather than templated.
*/ -}}
{{- define "keda.scalingIdentityName" -}}
metrics-api-worker-trigger
{{- end -}}

{{- /*
Whether the worker autoscaling identity should be rendered. KEDA scales Airflow workers,
which only run on a data plane.
Returns the string "true" or "false" — compare with eq.
*/ -}}
{{- define "keda.workerScalingEnabled" -}}
{{- and .Values.global.keda.enabled (eq (include "astronomer.dataPlaneEnabled" .) "true") -}}
{{- end -}}

{{- /*
Labels for the objects the platform creates in the KEDA namespace. The astronomer.io
prefixed label names the platform release that owns them, for anyone reading a namespace
the platform does not otherwise write to.
*/ -}}
{{- define "keda.scalingIdentityLabels" -}}
tier: astronomer
component: worker-autoscaling
release: {{ .Release.Name }}
chart: "{{ .Chart.Name }}-{{ .Chart.Version }}"
heritage: {{ .Release.Service }}
astronomer.io/platform-release: {{ .Release.Name }}
{{- end -}}

{{- /*
Common Helper template for data or unified mode
*/ -}}
{{- define "astronomer.dataPlaneEnabled" -}}
{{- if or (eq .Values.global.plane.mode "data") (eq .Values.global.plane.mode "unified") -}}
true
{{- end -}}
{{- end -}}

{{/*
Resolve whether a component should load its secrets from mounted files instead
of injecting them into the environment with valueFrom.secretKeyRef.

A component's own `secretsFromFiles.enabled` wins when it is explicitly set to a
boolean; otherwise `global.secretsFromFiles.enabled` applies. This lets an
operator flip the whole platform with one value while still holding back any
component whose image cannot read secrets from files yet.

Renders the string "true" or "false", so call it through `eq`:

  {{- $secretsFromFiles := eq "true" (include "secretsFromFiles.enabled" (dict "ctx" $ "component" .Values.commander)) }}
*/}}
{{- define "secretsFromFiles.enabled" -}}
{{- $component := get (get (.component | default dict) "secretsFromFiles" | default dict) "enabled" -}}
{{- $global := get (get (.ctx.Values.global | default dict) "secretsFromFiles" | default dict) "enabled" -}}
{{- if kindIs "bool" $component -}}
{{- $component -}}
{{- else if kindIs "bool" $global -}}
{{- $global -}}
{{- else -}}
false
{{- end -}}
{{- end }}

{{/*
The placeholder written into bootstrapper-managed Secrets by the chart, before
the ap-db-bootstrapper init container replaces it with a real connection string.

Deterministic on purpose: a random placeholder changes on every render, which
re-poisons the live Secret on `helm upgrade` and churns pod checksum annotations.
Consumers compare against this to tell "not bootstrapped yet" from a real value.
*/}}
{{- define "astronomer.secretSentinel" -}}
__ASTRONOMER_NOT_BOOTSTRAPPED__
{{- end }}

{{/*
The `connection` value for a Secret that the chart creates as a placeholder and an
in-pod bootstrapper init container later rewrites.

Two constraints pull against each other:

  - `helm upgrade` must not patch the bootstrapped value back to the placeholder.
  - The Secret must stay in the release manifest.

A `pre-install`-only hook satisfies the first and breaks the second: hook resources
are absent from the release manifest, so upgrading from a release where this Secret
WAS in the manifest makes Helm delete it. With secrets-from-files on, every consumer
then wedges on the missing volume before the bootstrapper that would recreate it can
run -- the same deadlock this placeholder exists to prevent, reached by a different
route. `helm.sh/resource-policy: keep` does not rescue it either: Helm reads that
annotation off the LIVE object, and the older release created that object without it.

So the Secret stays in the manifest and preserves whatever is already in the cluster.
A fresh install finds nothing and renders the sentinel; every later render finds the
bootstrapped value and renders it back byte-identical, so Helm patches nothing and the
consumers' checksum annotations do not churn.

`lookup` returns empty during `helm template` and client-side dry runs, which is why
tests see the sentinel. It is also why ArgoCD, which renders without cluster access,
re-applies the sentinel on every sync -- a limitation the hook form shared, tracked
separately.

Usage: {{ include "astronomer.bootstrapSecretConnection" (dict "ctx" $ "name" $secretName) }}
*/}}
{{- define "astronomer.bootstrapSecretConnection" -}}
{{- $existing := lookup "v1" "Secret" .ctx.Release.Namespace .name -}}
{{- $live := get (get ($existing | default dict) "data" | default dict) "connection" | default "" -}}
{{- if $live -}}
{{- /* Already base64 -- Secret .data is encoded, so pass it through untouched. */ -}}
{{- $live | quote -}}
{{- else -}}
{{- include "astronomer.secretSentinel" .ctx | b64enc | quote -}}
{{- end -}}
{{- end }}

{{/*
An init container that blocks until a bootstrapper-managed secret file holds a
real value rather than the sentinel.

Why this is needed: a `secret` volume is projected before ANY container runs,
and kubelet re-projects it asynchronously with no ordering guarantee against
container start. So a container that reads the file once at startup can latch
the sentinel written before the in-pod bootstrapper patched the Secret. Reading
the same secret via `valueFrom.secretKeyRef` never had this problem, because env
is resolved per-container at start, after all preceding init containers.

Measured on kind (k8s 1.37): when the bootstrapper's exit drives a pod sync the
refresh lands in well under a second; with no pod event at all it takes up to
kubelet's sync period, ~60s. So this gate is normally a no-op and worst case
adds about a minute to pod start.

Usage:
  {{- include "astronomer.waitForSecretFile" (dict "ctx" $ "image" (include "houston.image" $) "volume" "houston-secrets" "path" "/etc/astronomer/secrets/DATABASE_URL") | nindent 8 }}
*/}}
{{- define "astronomer.waitForSecretFile" -}}
- name: wait-for-secret
  image: {{ .image }}
  imagePullPolicy: IfNotPresent
  command:
    - /bin/sh
    - -c
    - |
      # Bounded so a genuinely stuck bootstrapper surfaces as a failed init
      # container rather than a pod that hangs in Init forever.
      deadline=$(( $(date +%s) + {{ .timeout | default 300 }} ))
      while [ "$(cat {{ .path }} 2>/dev/null)" = "{{ include "astronomer.secretSentinel" .ctx }}" ]; do
        if [ "$(date +%s)" -ge "$deadline" ]; then
          echo "timed out waiting for {{ .path }} to be bootstrapped" >&2
          exit 1
        fi
        echo "waiting for the bootstrapper to populate {{ .path }}"
        sleep 2
      done
  volumeMounts:
    - name: {{ .volume }}
      mountPath: {{ dir .path }}
      readOnly: true
{{- end }}

{{/*
`defaultMode` for every volume carrying a secret that a component reads from a
file.

0440 rather than Kubernetes' 0644 default: a world-readable file leaves the
secret open to every UID in the container, which gives back much of what moving
it out of the environment was meant to buy.

Not 0400 either. Kubernetes owns secret volume files as root:root, and these
pods run as non-root, so the process can only reach the file through its
fsGroup. Group read is load-bearing here -- 0400 makes the secret unreadable, and
the loaders fail closed on a file they were told to read but cannot: the
container exits instead of starting without its secret. Pair this with
astronomer.secretsFromFiles.podSecurityContext, which supplies the matching fsGroup.

Emitted as a bare octal literal on purpose: both Helm's and Kubernetes' YAML
parsers read it as YAML 1.1, where a leading zero means octal, matching the
`defaultMode: 0755` already used elsewhere in this chart.

Usage, at the same indentation as `sources:` or `secretName:`:
  {{- include "astronomer.secretsFromFiles.defaultMode" . | nindent 12 }}
*/}}
{{- define "astronomer.secretsFromFiles.defaultMode" -}}
defaultMode: 0440
{{- end }}

{{/*
The fsGroup a workload needs when it reads its secrets from mounted files, as an
override for platform.podSecurityContext to merge in:

  securityContext: {{- include "platform.podSecurityContext" (list $ (include "astronomer.secretsFromFiles.podSecurityContextOverride" (dict "ctx" $ "component" .Values.houston) | fromYaml)) | nindent 8 }}

The fsGroup is what makes astronomer.secretsFromFiles.defaultMode work: kubelet
chowns an ownership-managed volume to this group and adds the group to every
container's supplementary groups, so a 0440 root-owned file is readable by the
pod's processes and by nobody else. With no fsGroup at all the file stays
root:root and the process -- running as non-root -- cannot open it.

Any fsGroup does the job, so one the operator already set in podSecurityContext
is left alone rather than replaced. Omitted on OpenShift, which allocates an
fsGroup per namespace through its SecurityContextConstraints;
platform.podSecurityContext strips fsGroup there as well.

Resolves the component's toggle itself and renders nothing when it is off, so
every workload that mounts a secret volume can pass it unconditionally. That
matters because the set of such workloads is large and easy to under-count --
the houston family alone is over a dozen, most of them cronjobs. A pod that
mounts a 0440 secret without an fsGroup cannot read it, and the loaders fail
closed on an unreadable file, so a missing fsGroup is a container that never
starts rather than one quietly running on an environment variable the chart
already removed.

Renders YAML because include can only return a string, so pipe it through
fromYaml; an empty render becomes an empty dict, which merges as a no-op.
*/}}
{{- define "astronomer.secretsFromFiles.podSecurityContextOverride" -}}
{{- $readsFiles := false -}}
{{- if hasKey . "component" -}}
{{- $readsFiles = eq "true" (include "secretsFromFiles.enabled" (dict "ctx" .ctx "component" .component)) -}}
{{- end -}}
{{- /* A pod running an ap-db-bootstrapper init container needs the fsGroup for that
       container's file too, whatever the main component's own toggle says. */ -}}
{{- if and .dbBootstrapper (eq "true" (include "astronomer.dbBootstrapper.secretsFromFiles.enabled" .ctx)) -}}
{{- $readsFiles = true -}}
{{- end -}}
{{- if $readsFiles -}}
{{- if and (not ((.ctx.Values.global.openshift).enabled)) (not (hasKey (.ctx.Values.podSecurityContext | default dict) "fsGroup")) -}}
fsGroup: {{ ((.ctx.Values.global).secretsFromFiles).fsGroup | default 1000 }}
{{- end -}}
{{- end -}}
{{- end }}

{{/*
Whether the ap-db-bootstrapper init containers read BOOTSTRAP_DB from a mounted file.

Resolved from `global.dbBootstrapper.secretsFromFiles.enabled` through the usual
precedence, so it can inherit `global.secretsFromFiles.enabled`. Global rather than
per-subchart because the same image runs in the astronomer, grafana and laminar
subcharts, and one image either has the loader or does not.

Renders the string "true" or "false"; call it through `eq`. Takes the root context.
*/}}
{{- define "astronomer.dbBootstrapper.secretsFromFiles.enabled" -}}
{{- include "secretsFromFiles.enabled" (dict "ctx" . "component" ((.Values.global).dbBootstrapper)) -}}
{{- end }}

{{/*
The env entries an ap-db-bootstrapper init container gets for BOOTSTRAP_DB: either the
original secretKeyRef, or the loader's gate plus an explicit path to the mounted file.

No wait-for-secret gate is needed for this file, unlike the other bootstrapped
secrets. `astronomer-bootstrap` is never written by a bootstrapper: the bundled
postgresql chart renders it with its real value, or the operator creates it before
install, so it already holds the final value when the volume is projected.

Usage, at the indentation of the other env entries:
  {{- include "astronomer.dbBootstrapper.secretEnv" $ | nindent 12 }}
*/}}
{{- define "astronomer.dbBootstrapper.secretEnv" -}}
{{- if eq "true" (include "astronomer.dbBootstrapper.secretsFromFiles.enabled" .) -}}
- name: DB_BOOTSTRAPPER_SECRETS_FROM_FILES
  value: "true"
- name: BOOTSTRAP_DB_FILE
  value: /etc/astronomer/secrets/BOOTSTRAP_DB
{{- else -}}
- name: BOOTSTRAP_DB
  valueFrom:
    secretKeyRef:
      name: astronomer-bootstrap
      key: connection
{{- end -}}
{{- end }}

{{/*
The mount for an ap-db-bootstrapper init container's BOOTSTRAP_DB file. Renders
nothing when the toggle is off. Pair with astronomer.dbBootstrapper.secretVolume.
*/}}
{{- define "astronomer.dbBootstrapper.secretVolumeMount" -}}
{{- if eq "true" (include "astronomer.dbBootstrapper.secretsFromFiles.enabled" .) -}}
- name: db-bootstrapper-secret
  mountPath: /etc/astronomer/secrets
  readOnly: true
{{- end -}}
{{- end }}

{{/*
The pod volume carrying BOOTSTRAP_DB. Renders nothing when the toggle is off.

Callers must render it under the SAME condition as the bootstrapper container, not
merely the toggle. kubelet mounts every volume in a pod spec whether or not a
container uses it, and `astronomer-bootstrap` need not exist when an operator supplies
the backend secrets directly and the bootstrapper is skipped. An unused volume naming
a missing Secret would leave that pod stuck in ContainerCreating on FailedMount.

The pod also needs an fsGroup to read this 0440 file: pass "dbBootstrapper" true to
astronomer.secretsFromFiles.podSecurityContextOverride.
*/}}
{{- define "astronomer.dbBootstrapper.secretVolume" -}}
{{- if eq "true" (include "astronomer.dbBootstrapper.secretsFromFiles.enabled" .) -}}
- name: db-bootstrapper-secret
  secret:
    secretName: astronomer-bootstrap
    {{- include "astronomer.secretsFromFiles.defaultMode" . | nindent 4 }}
    items:
      - key: connection
        path: BOOTSTRAP_DB
{{- end -}}
{{- end }}
