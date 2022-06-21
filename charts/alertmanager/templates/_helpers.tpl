{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "alertmanager.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "alertmanager.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "alertmanager.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Image name.
*/}}
{{- define "alertmanager.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-alertmanager:{{ .Values.images.alertmanager.tag }}
{{- else -}}
{{ .Values.images.alertmanager.repository }}:{{ .Values.images.alertmanager.tag }}
{{- end -}}
{{- end -}}

{{ define "alertmanager.url" -}}
{{- if .Values.global.suffixDomain -}}
alertmanager-{{ .Values.global.suffixDomain }}.{{ .Values.global.baseDomain }}
{{- else -}}
alertmanager.{{ .Values.global.baseDomain }}
{{- end }}
{{- end }}

{{/*
Return  the proper Storage Class
*/}}
{{- define "alertmanager.storageClass" -}}
{{/*
Helm 2.11 supports the assignment of a value to a variable defined in a different scope,
but Helm 2.9 and 2.10 does not support it, so we need to implement this if-else logic.
*/}}
{{- if .Values.global.storageClass -}}
    {{- if (eq "-" .Values.global.storageClass) -}}
        {{- printf "storageClassName: \"\"" -}}
    {{- else }}
        {{- printf "storageClassName: %s" .Values.global.storageClass -}}
    {{- end -}}
{{- else -}}
    {{- if .Values.persistence.storageClassName -}}
          {{- if (eq "~" .Values.persistence.storageClassName) -}}
              {{- printf "storageClassName: \"\"" -}}
          {{- else }}
              {{- printf "storageClassName: %s" .Values.persistence.storageClassName -}}
          {{- end -}}
    {{- end -}}
{{- end -}}
{{- end -}}
