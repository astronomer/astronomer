{{- define "logging.indexNamePrefix" -}}
{{- if .Values.global.logging.indexNamePrefix -}}
{{- .Values.global.logging.indexNamePrefix -}}
{{- else -}}
{{- if .Values.global.loggingSidecar.enabled  -}}
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
{{ .Values.global.privateRegistry.repository }}/ap-dag-deploy:{{ .Values.global.dagOnlyDeployment.tag }}
{{- else -}}
{{ .Values.global.dagOnlyDeployment.repository }}:{{ .Values.global.dagOnlyDeployment.tag }}
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
{{- if or $ctx.Values.global.openshiftEnabled (eq (toString $base.runAsUser) "auto") -}}
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
{{- if $ctx.Values.global.openshiftEnabled -}}
{{- omit $base "fsGroup" "runAsGroup" "runAsUser" | toYaml -}}
{{- else -}}
{{- toYaml $base -}}
{{- end -}}
{{- end }}

{{ define "loggingSidecar.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-vector:{{ .Values.global.loggingSidecar.tag }}
{{- else -}}
{{ .Values.global.loggingSidecar.repository }}:{{ .Values.global.loggingSidecar.tag }}
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
