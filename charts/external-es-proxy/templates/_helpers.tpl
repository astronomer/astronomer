{{/*
Expand the name of the chart.
*/}}
{{- define "external-es-proxy.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "external-es-proxy.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "external-es-proxy.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "external-es-proxy.labels" -}}
helm.sh/chart: {{ include "external-es-proxy.chart" . }}
{{ include "external-es-proxy.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "external-es-proxy.selectorLabels" -}}
app.kubernetes.io/name: {{ include "external-es-proxy.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "external-es-proxy.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "external-es-proxy.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}


{{- define "external-es-proxy-trustcerts" -}}
{{- if .Values.global.customLogging.trustCaCerts  }}
{{- $secret_name := .Values.global.customLogging.trustCaCerts }}
  proxy_ssl_trusted_certificate /etc/ssl/certs/{{ $secret_name }}.pem;
  proxy_ssl_verify              on;
  proxy_ssl_verify_depth        2;
  proxy_ssl_session_reuse on;
{{- else }}
  proxy_ssl_verify              off;
{{- end }}
{{- end }}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "external-es-proxy.imagePullSecrets" -}}
{{- if and .Values.global.privateRegistry.enabled .Values.global.privateRegistry.secretName }}
imagePullSecrets:
  - name: {{ .Values.global.privateRegistry.secretName }}
{{- end -}}
{{- end -}}


{{ define "esproxy.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-openresty:{{ .Values.images.esproxy.tag }}
{{- else -}}
{{ printf "%s:%s" .Values.images.esproxy.repository .Values.images.esproxy.tag }}
{{- end }}
{{- end }}


{{ define "awsesproxy.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-awsesproxy:{{ .Values.images.awsproxy.tag }}
{{- else -}}
{{ printf "%s:%s" .Values.images.awsproxy.repository .Values.images.awsproxy.tag }}
{{- end }}
{{- end }}
