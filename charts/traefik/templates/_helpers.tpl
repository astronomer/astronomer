{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "traefik.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "traefik.fullname" -}}
{{- printf "%s-traefik" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Default backend fully qualified name.
*/}}
{{- define "traefik.defaultBackend.fullname" -}}
{{- printf "%s-traefik-default-backend" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "traefik.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Return the Traefik image string.
*/}}
{{- define "traefik.image" -}}
{{- printf "%s:%s" .Values.images.traefik.repository .Values.images.traefik.tag -}}
{{- end -}}

{{/*
Return the default backend image string.
*/}}
{{- define "traefik.defaultBackend.image" -}}
{{- printf "%s:%s" .Values.images.defaultBackend.repository .Values.images.defaultBackend.tag -}}
{{- end -}}

{{/*
IngressClass name — uses .Values.ingressClass if set, otherwise <release>-traefik.
*/}}
{{- define "traefik.ingress.class" -}}
{{- if .Values.ingressClass -}}
{{- .Values.ingressClass -}}
{{- else -}}
{{- template "traefik.fullname" . -}}
{{- end -}}
{{- end -}}

{{/*
ServiceAccount name.
*/}}
{{- define "traefik.serviceAccountName" -}}
{{- template "traefik.fullname" . -}}
{{- end -}}

{{/*
Image pull secrets.
*/}}
{{- define "traefik.imagePullSecrets" -}}
{{- if .Values.global.registrySecret }}
imagePullSecrets:
  - name: {{ .Values.global.registrySecret }}
{{- end -}}
{{- end -}}
