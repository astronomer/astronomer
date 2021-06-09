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
