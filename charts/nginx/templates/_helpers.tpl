{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "nginx.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "nginx.fullname" -}}
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
{{- define "nginx.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{ define "nginx.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-nginx:{{ .Values.images.nginx.tag }}
{{- else -}}
{{ .Values.images.nginx.repository }}:{{ .Values.images.nginx.tag }}
{{- end }}
{{- end }}

{{ define "nginx.defaultBackend.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-default-backend:{{ .Values.images.defaultBackend.tag }}
{{- else -}}
{{ .Values.images.defaultBackend.repository }}:{{ .Values.images.defaultBackend.tag }}
{{- end }}
{{- end }}

{{ define "nginx.ingress.class" -}}
{{- if .Values.ingressClass -}}
{{- .Values.ingressClass -}}
{{- else }}
{{- template "nginx.fullname" . -}}
{{- end -}}
{{- end -}}

{{ define "nginx.serviceAccountName" -}}
{{- if and .Values.serviceAccount.create .Values.global.rbacEnabled -}}
{{ default (printf "%s" (include "nginx.fullname" . )) .Values.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "nginx.imagePullSecrets" -}}
{{- if and .Values.global.privateRegistry.enabled .Values.global.privateRegistry.secretName }}
imagePullSecrets:
  - name: {{ .Values.global.privateRegistry.secretName }}
{{- end -}}
{{- end -}}

{{- define "defaultBackend.fullname" -}}
{{ printf "%s-default-backend" (include "nginx.fullname" .)}}
{{- end -}}

{{ define "defaultBackend.serviceAccountName" -}}
{{- if and .Values.defaultBackend.serviceAccount.create .Values.global.rbacEnabled -}}
{{ default (printf "%s" (include "defaultBackend.fullname" . )) .Values.defaultBackend.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.defaultBackend.serviceAccount.name }}
{{- end }}
{{- end }}
