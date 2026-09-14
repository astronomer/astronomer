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


{{ define "houston.internalauthurl" -}}
{{- if or (eq .Values.global.plane.mode "control") (eq .Values.global.plane.mode "unified") }}
nginx.ingress.kubernetes.io/auth-url: http://{{ .Release.Name }}-houston.{{ .Release.Namespace }}.svc.cluster.local:8871/v1/authorization
{{- else }}
nginx.ingress.kubernetes.io/auth-url: https://houston.{{ .Values.global.baseDomain }}/v1/authorization
{{- end }}
{{- end }}


{{ define "containerd.configToml" -}}
{{- .Values.global.privateCaCertsAddToHost.containerdConfigToml -}}
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

{{ define "loggingSidecar.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-vector:{{ .Values.global.logging.loggingSidecar.tag }}
{{- else -}}
{{ .Values.global.logging.loggingSidecar.repository }}:{{ .Values.global.logging.loggingSidecar.tag }}
{{- end }}
{{- end }}

{{ define "certCopier.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-base:{{ .Values.global.privateCaCertsAddToHost.certCopier.tag }}
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
proxy_pass https://houston.{{ .Values.global.baseDomain }}/v1/elasticsearch;
{{- end -}}
{{- end }}

{{ define "registry.authHeaderSecret" -}}
{{ default (printf "%s-registry-auth-key" .Release.Name) .Values.global.authHeaderSecretName }}
{{- end }}

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
fsGroup. Group read is load-bearing here -- 0400 makes the secret unreadable and
the loaders skip a file they cannot read, silently falling back to the
environment. Pair this with astronomer.secretsFromFiles.podSecurityContext,
which supplies the matching fsGroup.

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
Pod-level securityContext for a workload that reads its secrets from mounted
files.

The fsGroup is what makes astronomer.secretsFromFiles.defaultMode work: kubelet
chowns an ownership-managed volume to this group, so a 0440 file is readable by
the process and by nobody else. Without it the file stays root:root and the
process -- running as non-root -- cannot open it at all.

Omitted on OpenShift, which allocates an fsGroup per namespace through its
SecurityContextConstraints; a hardcoded value there is either rejected or
overridden, and the allocated one already matches the process.

Resolves the component's toggle itself and renders nothing when it is off, so
every workload that mounts a secret volume can include it unconditionally. That
matters because the set of such workloads is large and easy to under-count: the
houston family alone has 15, ten of them cronjobs. A pod that mounts a 0440
secret without an fsGroup cannot read it, and the loader treats an unreadable
file as "no secret configured" and falls back to an environment variable the
chart has already removed.

Usage:
  {{- include "astronomer.secretsFromFiles.podSecurityContext" (dict "ctx" $ "component" .Values.houston) | nindent 6 }}
*/}}
{{- define "astronomer.secretsFromFiles.podSecurityContext" -}}
{{- if eq "true" (include "secretsFromFiles.enabled" (dict "ctx" .ctx "component" .component)) -}}
{{- if not ((.ctx.Values.global.openshift).enabled) -}}
securityContext:
  fsGroup: {{ ((.ctx.Values.global).secretsFromFiles).fsGroup | default 1000 }}
{{- end -}}
{{- end -}}
{{- end }}
