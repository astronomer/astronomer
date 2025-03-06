{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "elasticsearch.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 44 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 44 chars (63 - len("-headless-discovery")) because some Kubernetes name fields are limited to 63 (by the DNS naming spec).
*/}}
{{- define "elasticsearch.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 44 | trimSuffix "-" -}}
{{- end -}}

{{ define "elasticsearch.serviceAccountName" -}}
{{- if and .Values.common.serviceAccount.create .Values.global.rbacEnabled -}}
{{ default (printf "%s" (include "elasticsearch.fullname" . )) .Values.common.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.common.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "elasticsearch.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Init image name.
*/}}
{{- define "init.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-base:{{ .Values.images.init.tag }}
{{- else -}}
{{ .Values.images.init.repository }}:{{ .Values.images.init.tag }}
{{- end -}}
{{- end -}}

{{/*
Elasticsearch image name.
*/}}
{{- define "elasticsearch.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-elasticsearch:{{ .Values.images.es.tag }}
{{- else -}}
{{ .Values.images.es.repository }}:{{ .Values.images.es.tag }}
{{- end -}}
{{- end -}}

{{/*
Curator image name.
*/}}
{{- define "curator.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-curator:{{ .Values.images.curator.tag }}
{{- else -}}
{{ .Values.images.curator.repository }}:{{ .Values.images.curator.tag }}
{{- end -}}
{{- end -}}

{{/*
Exporter image name.
*/}}
{{- define "exporter.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-elasticsearch-exporter:{{ .Values.images.exporter.tag }}
{{- else -}}
{{ .Values.images.exporter.repository }}:{{ .Values.images.exporter.tag }}
{{- end -}}
{{- end -}}

{{/*
Nginx image name.
*/}}
{{ define "nginx-es.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-nginx-es:{{ .Values.images.nginx.tag }}
{{- else -}}
{{ .Values.images.nginx.repository }}:{{ .Values.images.nginx.tag }}
{{- end }}
{{- end }}

{{/*
Elasticsearch NGINX variable definitions
*/}}

{{- define "nginx-es.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "nginx-es.fullname" -}}
{{- if .Values.nginx.fullnameOverride -}}
{{- .Values.nginx.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "nginx-es.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Return  the proper Storage Class
*/}}
{{- define "elasticsearch.storageClass" -}}
storageClassName: {{ or .Values.common.persistence.storageClassName .Values.global.storageClass | default "" }}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "elasticsearch.imagePullSecrets" -}}
{{- if and .Values.global.privateRegistry.enabled .Values.global.privateRegistry.secretName }}
imagePullSecrets:
  - name: {{ .Values.global.privateRegistry.secretName }}
{{- end -}}
{{- end -}}
{{- define "elasticsearch.master.roles" -}}
{{- range $.Values.master.roles -}}
{{ . }},
{{- end -}}
{{- end -}}

{{- define "elasticsearch.data.roles" -}}
{{- range $.Values.data.roles -}}
{{ . }},
{{- end -}}
{{- end -}}

{{- define "elasticsearch.client.roles" -}}
{{- range $.Values.client.roles -}}
{{ . }},
{{- end -}}
{{- end -}}

{{- define "curator.indexPattern" -}}
{{ if and .Values.global.loggingSidecar.enabled  .Values.global.loggingSidecar.indexPattern }}
{{- .Values.global.loggingSidecar.indexPattern | squote }}
{{ else }}
{{- .Values.curator.age.timestring | squote}}
{{- end -}}
{{- end -}}

{{- define "elasticsearch.securityContext" -}}
{{- if or (eq ( toString ( .Values.securityContext.runAsUser )) "auto") ( .Values.global.openshiftEnabled ) }}
{{- omit  .Values.securityContext "runAsUser" | toYaml | nindent 10 }}
{{- else }}
{{- .Values.securityContext | toYaml | nindent 10 }}
{{- end -}}
{{- end }}
