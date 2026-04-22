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
proxy_pass https://houston.{{ .Values.global.baseDomain }}/v1/elasticsearch;
{{- end -}}
{{- end }}

{{ define "registry.authHeaderSecret" -}}
{{ default (printf "%s-registry-auth-key" .Release.Name) .Values.global.authHeaderSecretName }}
{{- end }}
