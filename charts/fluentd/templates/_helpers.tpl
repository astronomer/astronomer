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

{{ define "fluentd.serviceAccountName" -}}
{{- if and .Values.serviceAccount.create .Values.global.rbacEnabled -}}
{{ default (printf "%s" (include "fluentd.fullname" . )) .Values.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

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

{{- define "fluentd.s3Config" }}
<assume_role_credentials>
  role_arn {{ .Values.s3.role_arn }}
  role_session_name {{ .Values.s3.role_session_name }}
</assume_role_credentials>
s3_bucket {{ .Values.s3.s3_bucket }}
s3_region {{ .Values.s3.s3_region }}
{{- if .Values.s3.path }}
path {{ .Values.s3.path }}
{{- end }}
{{- if .Values.s3.use_server_side_encryption }}
use_server_side_encryption {{ .Values.s3.use_server_side_encryption }}
{{- end }}
{{- end }}

{{- define "custom_ca_volume_mounts" }}
{{ if .Values.global.privateCaCerts }}
{{ range $secret_name := (.Values.global.privateCaCerts) }}
- name: {{ $secret_name }}
  mountPath: /usr/local/share/ca-certificates/{{ $secret_name }}.pem
  subPath: cert.pem
{{- end }}
{{- end }}
{{- end }}

{{- define "custom_ca_volumes"}}
{{ if .Values.global.privateCaCerts }}
{{ range .Values.global.privateCaCerts }}
- name: {{ . }}
  secret:
    secretName: {{ . }}
{{- end }}
{{- end }}
{{- end }}


{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "fluentd.imagePullSecrets" -}}
{{- if and .Values.global.privateRegistry.enabled .Values.global.privateRegistry.secretName }}
imagePullSecrets:
  - name: {{ .Values.global.privateRegistry.secretName }}
{{- end -}}
{{- end -}}

{{- define "fluentd.indexNamePrefix" -}}
{{- if .Values.global.logging.indexNamePrefix -}}
{{ .Values.global.logging.indexNamePrefix }}
{{- else -}}
fluentd
{{- end -}}
{{- end -}}
