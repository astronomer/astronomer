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
alertmanager.{{ .Values.global.baseDomain }}
{{- end }}

{{/*
Return  the proper Storage Class
*/}}
{{- define "alertmanager.storageClass" -}}
storageClassName: {{ or .Values.persistence.storageClassName .Values.global.storageClass | default "" }}
{{- end -}}


{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "alertmanager.imagePullSecrets" -}}
{{- if and .Values.global.privateRegistry.enabled .Values.global.privateRegistry.secretName }}
imagePullSecrets:
  - name: {{ .Values.global.privateRegistry.secretName }}
{{- end -}}
{{- end -}}

{{- define "alertmanager.custom_ca_volume_mounts" }}
{{ if .Values.global.privateCaCerts }}
{{- range $secret_name := (.Values.global.privateCaCerts) }}
- name: {{ $secret_name }}
  mountPath: /usr/local/share/ca-certificates/{{ $secret_name }}.pem
  subPath: cert.pem
{{- end }}
{{- end }}
{{- end }}

{{- define "alertmanager.custom_ca_volumes"}}
{{ if .Values.global.privateCaCerts }}
{{- range .Values.global.privateCaCerts }}
- name: {{ . }}
  secret:
    secretName: {{ . }}
{{- end }}
{{- end }}
{{- end }}

{{ define "alertmanager.serviceAccountName" -}}
{{- if and .Values.serviceAccount.create .Values.global.rbacEnabled -}}
{{ default (printf "%s" (include "alertmanager.fullname" . )) .Values.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
