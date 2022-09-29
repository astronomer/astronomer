{{/*
Expand the name of the chart.
*/}}
{{- define "nats.name" -}}
{{ .Release.Name | trunc 63 | trimSuffix "-" -}}-{{ .Chart.Name }}
{{- end -}}

{{/*
Return the proper NATS image name
*/}}
{{- define "nats.clusterAdvertise" -}}
{{- printf "$(POD_NAME).%s.$(POD_NAMESPACE).svc" (include "nats.name" . ) }}
{{- end }}

{{/*
Return the NATS cluster routes.
*/}}
{{- define "nats.clusterRoutes" -}}
{{- $name := printf "%s-%s" (.Release.Name | trunc 63 | trimSuffix "-") .Chart.Name -}}
{{- range $i, $e := until (.Values.global.nats.replicas | int) -}}
{{- printf "nats://%s-%d.%s.%s.svc:6222," $name $i $name $.Release.Namespace -}}
{{- end -}}
{{- end }}

{{ define "nats-exporter.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-nats-exporter:{{ .Values.images.exporter.tag }}
{{- else -}}
{{ .Values.images.exporter.repository }}:{{ .Values.images.exporter.tag }}
{{- end }}
{{- end }}

{{ define "nats.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-nats-server:{{ .Values.images.nats.tag }}
{{- else -}}
{{ .Values.images.nats.repository }}:{{ .Values.images.nats.tag }}
{{- end }}
{{- end }}

{{ define "nats.init.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-base:{{ .Values.images.init.tag }}
{{- else -}}
{{ .Values.images.init.repository }}:{{ .Values.images.init.tag }}
{{- end }}
{{- end }}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "nats.imagePullSecrets" -}}
{{- if and .Values.global.privateRegistry.enabled .Values.global.privateRegistry.secretName }}
imagePullSecrets:
  - name: {{ .Values.global.privateRegistry.secretName }}
{{- end -}}
{{- end -}}
