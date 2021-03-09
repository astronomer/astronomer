{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "stan.name" -}}
{{ .Release.Name | trunc 63 | trimSuffix "-" -}}-{{ .Chart.Name }}
{{- end -}}

{{/*
Return the list of peers in a NATS Streaming cluster.
*/}}
{{- define "stan.clusterPeers" -}}
{{- range $i, $e := until (int $.Values.global.stan.replicas) -}}
{{- printf "'%s-%d'," (include "stan.name" $) $i -}}
{{- end -}}
{{- end }}

{{- define "stan.replicaCount" -}}
{{- $replicas := (int $.Values.global.stan.replicas) -}}
{{- if and $.Values.store.cluster.enabled (lt $replicas 3) -}}
{{- $replicas = "" -}}
{{- end -}}
{{ print $replicas }}
{{- end -}}

{{ define "stan.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-stan:{{ .Values.images.stan.tag }}
{{- else -}}
{{ .Values.images.stan.repository }}:{{ .Values.images.stan.tag }}
{{- end }}
{{- end }}

{{ define "stan.init.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-base:{{ .Values.images.init.tag }}
{{- else -}}
{{ .Values.images.init.repository }}:{{ .Values.images.init.tag }}
{{- end }}
{{- end }}
