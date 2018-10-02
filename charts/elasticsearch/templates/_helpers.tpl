{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 53 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 53 chars (63 - len("-discovery")) because some Kubernetes name fields are limited to 63 (by the DNS naming spec).
*/}}
{{- define "fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 53 | trimSuffix "-" -}}
{{- end -}}

{{/*
Return the appropriate apiVersion for Curactor cron job.
Could use .Capabilities.KubeVersion.Minor in future.
*/}}
{{- define "curator.cronJob.apiVersion" -}}
"batch/v1beta1"
{{- end -}}

{{/*
Init image name.
*/}}
{{- define "init.image" -}}
{{ .Values.images.init.repository }}:{{ .Values.images.init.tag }}
{{- end -}}

{{/*
Elasticsearch image name.
*/}}
{{- define "elasticsearch.image" -}}
{{ .Values.images.es.repository }}:{{ .Values.images.es.tag }}
{{- end -}}

{{/*
Curator image name.
*/}}
{{- define "curator.image" -}}
{{ .Values.images.curator.repository }}:{{ .Values.images.curator.tag }}
{{- end -}}

{{/*
Exporter image name.
*/}}
{{- define "exporter.image" -}}
{{ .Values.images.exporter.repository }}:{{ .Values.images.exporter.tag }}
{{- end -}}
