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


{{/*
Option to add trust certs when privateCA or self signed certs are used
with hosted elastic search. By defaults it is off when trustCaCerts are
provided it will use that certs to trust the connection
*/}}

{{- define "external-es-proxy-trustcerts" -}}
{{- if .Values.global.customLogging.trustCaCerts }}
{{- $secret_name := .Values.global.customLogging.trustCaCerts }}
proxy_ssl_trusted_certificate /etc/ssl/certs/{{ $secret_name }}.pem;
proxy_ssl_verify on;
proxy_ssl_verify_depth 2;
proxy_ssl_session_reuse on;
{{- else }}
proxy_ssl_verify off;
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
{{ .Values.images.esproxy.repository}}:{{ .Values.images.esproxy.tag }}
{{- end }}
{{- end }}


{{ define "awsesproxy.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-awsesproxy:{{ .Values.images.awsproxy.tag }}
{{- else -}}
{{ .Values.images.awsproxy.repository }}:{{ .Values.images.awsproxy.tag }}
{{- end }}
{{- end }}


{{/*
Switches the elasticsearch configuratiob based on customLogging
when aws managed elastic search is confired awsesproxy settings is required
to authenticate with aws managed elastic search or opensearch
*/}}

{{- define "external-es-proxy-nginx-location-common" -}}
{{- if or .Values.global.customLogging.awsSecretName .Values.global.customLogging.awsServiceAccountAnnotation .Values.global.customLogging.awsIAMRole }}
proxy_pass http://localhost:{{ .Values.service.awsproxy }};
{{- else }}
access_by_lua_file /usr/local/openresty/nginx/conf/setenv.lua;
proxy_pass {{.Values.global.customLogging.scheme}}://{{.Values.global.customLogging.host}}:{{.Values.global.customLogging.port}};
{{- include "external-es-proxy-trustcerts" . }}
{{- end }}
{{- end }}
