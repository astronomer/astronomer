{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "postgresql.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "postgresql.fullname" -}}
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
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "postgresql.master.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- $fullname := default (printf "%s-%s" .Release.Name $name) .Values.fullnameOverride -}}
{{- if .Values.replication.enabled -}}
{{- printf "%s-%s" $fullname "master" | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s" $fullname | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Return the appropriate apiVersion for networkpolicy.
*/}}
{{- define "postgresql.networkPolicy.apiVersion" -}}
"networking.k8s.io/v1"
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "postgresql.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Return the proper PostgreSQL image name
*/}}
{{- define "postgresql.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-postgresql:{{ .Values.image.tag }}
{{- else -}}
{{ .Values.image.registry }}/{{ .Values.image.repository }}:{{ .Values.image.tag }}
{{- end }}
{{- end }}

{{/*
Return PostgreSQL password
*/}}
{{- define "postgresql.password" -}}
{{- if .Values.global.postgresql.postgresqlPassword }}
    {{- .Values.global.postgresql.postgresqlPassword -}}
{{- else if .Values.postgresqlPassword -}}
    {{- .Values.postgresqlPassword -}}
{{- else -}}
    {{- randAlphaNum 10 -}}
{{- end -}}
{{- end -}}

{{/*
Return PostgreSQL replication password
*/}}
{{- define "postgresql.replication.password" -}}
{{- if .Values.global.postgresql.replicationPassword }}
    {{- .Values.global.postgresql.replicationPassword -}}
{{- else if .Values.replication.password -}}
    {{- .Values.replication.password -}}
{{- else -}}
    {{- randAlphaNum 10 -}}
{{- end -}}
{{- end -}}

{{/*
Return PostgreSQL username
*/}}
{{- define "postgresql.username" -}}
{{- if .Values.global.postgresql.postgresqlUsername }}
    {{- .Values.global.postgresql.postgresqlUsername -}}
{{- else -}}
    {{- .Values.postgresqlUsername -}}
{{- end -}}
{{- end -}}


{{/*
Return PostgreSQL replication username
*/}}
{{- define "postgresql.replication.username" -}}
{{- if .Values.global.postgresql.replicationUser }}
    {{- .Values.global.postgresql.replicationUser -}}
{{- else -}}
    {{- .Values.replication.user -}}
{{- end -}}
{{- end -}}

{{/*
Return PostgreSQL port
*/}}
{{- define "postgresql.port" -}}
{{- if .Values.global.postgresql.servicePort }}
    {{- .Values.global.postgresql.servicePort -}}
{{- else -}}
    {{- .Values.service.port -}}
{{- end -}}
{{- end -}}

{{/*
Return PostgreSQL created database
*/}}
{{- define "postgresql.database" -}}
{{- if .Values.global.postgresql.postgresqlDatabase }}
    {{- .Values.global.postgresql.postgresqlDatabase -}}
{{- else if .Values.postgresqlDatabase -}}
    {{- .Values.postgresqlDatabase -}}
{{- end -}}
{{- end -}}

{{/*
Return the proper image name to change the volume permissions
*/}}
{{- define "postgresql.volumePermissions.image" -}}
{{- $registryName := .Values.volumePermissions.image.registry -}}
{{- $repositoryName := .Values.volumePermissions.image.repository -}}
{{- $tag := .Values.volumePermissions.image.tag | toString -}}
{{/*
Helm 2.11 supports the assignment of a value to a variable defined in a different scope,
but Helm 2.9 and 2.10 doesn't support it, so we need to implement this if-else logic.
Also, we can't use a single if because lazy evaluation is not an option
*/}}
{{- if .Values.global }}
    {{- if .Values.global.imageRegistry }}
        {{- printf "%s/%s:%s" .Values.global.imageRegistry $repositoryName $tag -}}
    {{- else -}}
        {{- printf "%s/%s:%s" $registryName $repositoryName $tag -}}
    {{- end -}}
{{- else -}}
    {{- printf "%s/%s:%s" $registryName $repositoryName $tag -}}
{{- end -}}
{{- end -}}

{{/*
Return the proper PostgreSQL metrics image name
*/}}
{{- define "postgresql.metrics.image" -}}
{{- $registryName :=  default "docker.io" .Values.metrics.image.registry -}}
{{- $repositoryName := .Values.metrics.image.repository -}}
{{- $tag := default "latest" .Values.metrics.image.tag | toString -}}
{{/*
Helm 2.11 supports the assignment of a value to a variable defined in a different scope,
but Helm 2.9 and 2.10 doesn't support it, so we need to implement this if-else logic.
Also, we can't use a single if because lazy evaluation is not an option
*/}}
{{- if .Values.global }}
    {{- if .Values.global.imageRegistry }}
        {{- printf "%s/%s:%s" .Values.global.imageRegistry $repositoryName $tag -}}
    {{- else -}}
        {{- printf "%s/%s:%s" $registryName $repositoryName $tag -}}
    {{- end -}}
{{- else -}}
    {{- printf "%s/%s:%s" $registryName $repositoryName $tag -}}
{{- end -}}
{{- end -}}

{{/*
Get the password secret.
*/}}
{{- define "postgresql.secretName" -}}
{{- if .Values.global.postgresql.existingSecret }}
    {{- printf "%s" .Values.global.postgresql.existingSecret -}}
{{- else if .Values.existingSecret -}}
    {{- printf "%s" .Values.existingSecret -}}
{{- else -}}
    {{- printf "%s" (include "postgresql.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Return true if a secret object should be created
*/}}
{{- define "postgresql.createSecret" -}}
{{- if .Values.global.postgresql.existingSecret }}
{{- else if .Values.existingSecret -}}
{{- else -}}
    {{- true -}}
{{- end -}}
{{- end -}}

{{/*
Get the configuration ConfigMap name.
*/}}
{{- define "postgresql.configurationCM" -}}
{{- if .Values.configurationConfigMap -}}
{{- printf "%s" (tpl .Values.configurationConfigMap $) -}}
{{- else -}}
{{- printf "%s-configuration" (include "postgresql.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Get the extended configuration ConfigMap name.
*/}}
{{- define "postgresql.extendedConfigurationCM" -}}
{{- if .Values.extendedConfConfigMap -}}
{{- printf "%s" (tpl .Values.extendedConfConfigMap $) -}}
{{- else -}}
{{- printf "%s-extended-configuration" (include "postgresql.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Get the initialization scripts ConfigMap name.
*/}}
{{- define "postgresql.initdbScriptsCM" -}}
{{- if .Values.initdbScriptsConfigMap -}}
{{- printf "%s" (tpl .Values.initdbScriptsConfigMap $) -}}
{{- else -}}
{{- printf "%s-init-scripts" (include "postgresql.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
Get the initialization scripts Secret name.
*/}}
{{- define "postgresql.initdbScriptsSecret" -}}
{{- printf "%s" (tpl .Values.initdbScriptsSecret $) -}}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "postgresql.imagePullSecrets" -}}
{{/*
Helm 2.11 supports the assignment of a value to a variable defined in a different scope,
but Helm 2.9 and 2.10 does not support it, so we need to implement this if-else logic.
Also, we can not use a single if because lazy evaluation is not an option
*/}}
{{- if .Values.global }}
{{- if and .Values.global.privateRegistry.enabled .Values.global.privateRegistry.secretName }}
imagePullSecrets:
  - name: {{ .Values.global.privateRegistry.secretName }}
{{- else if or .Values.global.imagePullSecrets .Values.image.pullSecrets .Values.metrics.image.pullSecrets .Values.volumePermissions.image.pullSecrets }}
imagePullSecrets:
{{- range .Values.image.pullSecrets }}
  - name: {{ . }}
{{- end }}
{{- range .Values.metrics.image.pullSecrets }}
  - name: {{ . }}
{{- end }}
{{- range .Values.volumePermissions.image.pullSecrets }}
  - name: {{ . }}
{{- end }}
{{- end -}}
{{- else if or .Values.image.pullSecrets .Values.metrics.image.pullSecrets .Values.volumePermissions.image.pullSecrets }}
imagePullSecrets:
{{- range .Values.image.pullSecrets }}
  - name: {{ . }}
{{- end }}
{{- range .Values.metrics.image.pullSecrets }}
  - name: {{ . }}
{{- end }}
{{- range .Values.volumePermissions.image.pullSecrets }}
  - name: {{ . }}
{{- end }}
{{- end -}}
{{- end -}}

{{/*
Get the readiness probe command
*/}}
{{- define "postgresql.readinessProbeCommand" -}}
- |
{{- if (include "postgresql.database" .) }}
  pg_isready -U {{ include "postgresql.username" . | quote }} -d {{ (include "postgresql.database" .) | quote }} -h 127.0.0.1 -p {{ template "postgresql.port" . }}
{{- else }}
  pg_isready -U {{ include "postgresql.username" . | quote }} -h 127.0.0.1 -p {{ template "postgresql.port" . }}
{{- end }}
{{- if contains "bitnami/" .Values.image.repository }}
  [ -f /opt/bitnami/postgresql/tmp/.initialized ]
{{- end -}}
{{- end -}}

{{/*
Return  the proper Storage Class
*/}}
{{- define "postgresql.storageClass" -}}
storageClassName: {{ or .Values.persistence.storageClass .Values.global.storageClass | default "" }}
{{- end -}}

{{ define "postgresql.serviceAccountName" -}}
{{- if and .Values.serviceAccount.create .Values.global.rbacEnabled -}}
{{ default (printf "%s" (include "postgresql.fullname" . )) .Values.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
