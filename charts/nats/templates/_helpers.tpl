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

{{ define "dbBootstrapper.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-db-bootstrapper:{{ .Values.images.dbBootstrapper.tag }}
{{- else -}}
{{ .Values.images.dbBootstrapper.repository }}:{{ .Values.images.dbBootstrapper.tag }}
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

{{ define "nats.jestreamTLSSecret" -}}
{{ default (printf "%s-jetstream-tls-certificate" .Release.Name)}}
{{- end }}

{{- define "nats.securityContext" -}}
{{- if or (eq ( toString ( .Values.securityContext.runAsUser )) "auto") ( .Values.global.openshiftEnabled ) }}
{{- omit  .Values.securityContext "runAsUser" | toYaml | nindent 10 }}
{{- else }}
{{- .Values.securityContext | toYaml | nindent 10 }}
{{- end -}}
{{- end }}


{{ define "nats.serviceAccountName" -}}
{{- if and .Values.nats.serviceAccount.create .Values.global.rbacEnabled -}}
{{ default (printf "%s" (include "nats.name" . )) .Values.nats.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.nats.serviceAccount.name }}
{{- end }}
{{- end }}

{{ define "jetStream.serviceAccountName" -}}
{{- if and .Values.nats.jetstream.serviceAccount.create .Values.global.rbacEnabled -}}
{{ default (printf "%s-jetstream-sa" .Release.Name) .Values.nats.jetstream.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.nats.jetstream.serviceAccount.name }}
{{- end }}
{{- end }}
