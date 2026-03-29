{{/*
Expand the name of the chart.
*/}}
{{- define "external-secrets.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "external-secrets.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Define namespace of chart, useful for multi-namespace deployments
*/}}
{{- define "external-secrets.namespace" -}}
{{- if .Values.namespaceOverride }}
{{- .Values.namespaceOverride }}
{{- else }}
{{- .Release.Namespace }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "external-secrets.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "external-secrets.labels" -}}
helm.sh/chart: {{ include "external-secrets.chart" . }}
{{ include "external-secrets.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "external-secrets.selectorLabels" -}}
app.kubernetes.io/name: {{ include "external-secrets.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "external-secrets.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "external-secrets.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Determine the image to use, including if using a flavour.
*/}}
{{- define "external-secrets.image" -}}
{{- $imageBasename := .image.repository | splitList "/" | last -}}
{{- $repository := "" -}}
{{- if and .context.Values.global.privateRegistry .context.Values.global.privateRegistry.enabled -}}
{{- $repository = printf "%s/%s" .context.Values.global.privateRegistry.repository $imageBasename -}}
{{- else if .context.Values.global.repository -}}
{{- $repository = .context.Values.global.repository -}}
{{- else -}}
{{- $repository = .image.repository -}}
{{- end -}}
{{- if .image.flavour -}}
{{ printf "%s:%s-%s" $repository (.image.tag | default .chartAppVersion) .image.flavour }}
{{- else }}
{{ printf "%s:%s" $repository (.image.tag | default .chartAppVersion) }}
{{- end }}
{{- end }}

{{/*
Renders a complete tree, even values that contains template.
*/}}
{{- define "external-secrets.render" -}}
  {{- if typeIs "string" .value }}
    {{- tpl .value .context }}
  {{ else }}
    {{- tpl (.value | toYaml) .context }}
  {{- end }}
{{- end -}}

{{/*
Return true if the OpenShift is the detected platform
Usage:
{{- include "external-secrets.isOpenShift" . -}}
*/}}
{{- define "external-secrets.isOpenShift" -}}
{{- if .Capabilities.APIVersions.Has "security.openshift.io/v1" -}}
{{- true -}}
{{- end -}}
{{- end -}}

{{/*
Render the securityContext based on the provided securityContext
  {{- include "external-secrets.renderSecurityContext" (dict "securityContext" .Values.securityContext "context" $) -}}
*/}}
{{- define "external-secrets.renderSecurityContext" -}}
{{- $adaptedContext := .securityContext -}}
{{- if .context.Values.global.compatibility -}}
  {{- if .context.Values.global.compatibility.openshift -}}
    {{- if or (eq .context.Values.global.compatibility.openshift.adaptSecurityContext "force") (and (eq .context.Values.global.compatibility.openshift.adaptSecurityContext "auto") (include "external-secrets.isOpenShift" .context)) -}}
      {{/* Remove OpenShift managed fields */}}
      {{- $adaptedContext = omit $adaptedContext "fsGroup" "runAsUser" "runAsGroup" -}}
      {{- if not .securityContext.seLinuxOptions -}}
        {{- $adaptedContext = omit $adaptedContext "seLinuxOptions" -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- omit $adaptedContext "enabled" | toYaml -}}
{{- end -}}

{{/*
Create the name of the pod disruption budget to use
*/}}
{{- define "external-secrets.pdbName" -}}
{{- .Values.podDisruptionBudget.nameOverride | default (printf "%s-pdb" (include "external-secrets.fullname" .)) }}
{{- end }}

{{/*
Fail the install if a cluster scoped reconciler is enabled while its namespace scoped counterpart is disabled
*/}}
{{- define "external-secrets.reconciler-sanity-test" -}}
{{- if and (not .Values.processPushSecret) .Values.processClusterPushSecret -}}
  {{- fail "You have disabled processing of PushSecrets but not ClusterPushSecrets. This is an invalid configuration. ClusterPushSecret processing depends on processing of PushSecrets. Please either enable processing of PushSecrets, or disable processing of ClusterPushSecrets." }}
{{- end -}}
{{- end -}}
