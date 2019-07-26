{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "fluentd.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "fluentd.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "fluentd.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Return the elasticsearch hostname
*/}}
{{- define "elasticsearch.host" -}}
{{- printf "%s-%s" .Release.Name "elasticsearch" -}}
{{- end -}}

{{/*
Full image name.
*/}}
{{- define "fluentd.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-fluentd:{{ .Values.images.fluentd.tag }}
{{- else -}}
{{ .Values.images.fluentd.repository }}:{{ .Values.images.fluentd.tag }}
{{- end -}}
{{- end -}}
