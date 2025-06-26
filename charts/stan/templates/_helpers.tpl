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
{{ .Values.global.privateRegistry.repository }}/ap-nats-streaming:{{ .Values.images.stan.tag }}
{{- else -}}
{{ .Values.images.stan.repository }}:{{ .Values.images.stan.tag }}
{{- end }}
{{- end }}

{{ define "stan.init.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-init:{{ .Values.images.init.tag }}
{{- else -}}
{{ .Values.images.init.repository }}:{{ .Values.images.init.tag }}
{{- end }}
{{- end }}

{{/*
Return  the proper Storage Class
*/}}
{{- define "stan.storageClass" -}}
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
    {{- if .Values.store.volume.storageClass -}}
          {{- if (eq "-" .Values.store.volume.storageClass) -}}
              {{- printf "storageClassName: \"\"" -}}
          {{- else }}
              {{- printf "storageClassName: %s" .Values.store.volume.storageClass -}}
          {{- end -}}
    {{- end -}}
{{- end -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "stan.imagePullSecrets" -}}
{{- if and .Values.global.privateRegistry.enabled .Values.global.privateRegistry.secretName }}
imagePullSecrets:
  - name: {{ .Values.global.privateRegistry.secretName }}
{{- end -}}
{{- end -}}

{{ define "stan.serviceAccountName" -}}
{{- if and .Values.stan.serviceAccount.create .Values.global.rbacEnabled -}}
{{ default (printf "%s" (include "stan.name" . )) .Values.stan.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.stan.serviceAccount.name }}
{{- end }}
{{- end }}
