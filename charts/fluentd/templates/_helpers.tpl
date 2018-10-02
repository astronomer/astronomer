{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Return the elasticsearch hostname
*/}}
{{- define "elasticsearch_host" -}}
{{- printf "%s-%s" .Release.Name "elasticsearch" -}}
{{- end -}}

{{/*
Full image name.
*/}}
{{- define "fluentd_image" -}}
{{ .Values.images.fluentd.repository }}:{{ .Values.images.fluentd.tag }}
{{- end -}}
