{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "elasticsearch.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 44 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 44 chars (63 - len("-headless-discovery")) because some Kubernetes name fields are limited to 63 (by the DNS naming spec).
*/}}
{{- define "elasticsearch.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 44 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{ define "elasticsearch.serviceAccountName" -}}
{{- if and .Values.common.serviceAccount.create .Values.global.rbac.enabled -}}
{{ default (printf "%s" (include "elasticsearch.fullname" . )) .Values.common.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.common.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "elasticsearch.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Init image name.
*/}}
{{- define "init.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-base:{{ .Values.images.init.tag }}
{{- else -}}
{{ .Values.images.init.repository }}:{{ .Values.images.init.tag }}
{{- end -}}
{{- end -}}

{{/*
Elasticsearch image name.
*/}}
{{- define "elasticsearch.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-elasticsearch:{{ .Values.images.es.tag }}
{{- else -}}
{{ .Values.images.es.repository }}:{{ .Values.images.es.tag }}
{{- end -}}
{{- end -}}

{{/*
Curator image name.
*/}}
{{- define "curator.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-curator:{{ .Values.images.curator.tag }}
{{- else -}}
{{ .Values.images.curator.repository }}:{{ .Values.images.curator.tag }}
{{- end -}}
{{- end -}}

{{/*
Exporter image name.
*/}}
{{- define "exporter.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-elasticsearch-exporter:{{ .Values.images.exporter.tag }}
{{- else -}}
{{ .Values.images.exporter.repository }}:{{ .Values.images.exporter.tag }}
{{- end -}}
{{- end -}}

{{/*
Nginx image name.
*/}}
{{ define "nginx-es.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-nginx-es:{{ .Values.images.nginx.tag }}
{{- else -}}
{{ .Values.images.nginx.repository }}:{{ .Values.images.nginx.tag }}
{{- end }}
{{- end }}

{{/*
Elasticsearch NGINX variable definitions
*/}}

{{- define "nginx-es.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "nginx-es.fullname" -}}
{{- if .Values.nginx.fullnameOverride -}}
{{- .Values.nginx.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "nginx-es.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Return the proper Storage Class
*/}}
{{- define "elasticsearch.storageClass" -}}
storageClassName: {{ or .Values.common.persistence.storageClassName .Values.global.storageClass | default "" }}
{{- end -}}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "elasticsearch.imagePullSecrets" -}}
{{- if and .Values.global.privateRegistry.enabled .Values.global.privateRegistry.secretName }}
imagePullSecrets:
  - name: {{ .Values.global.privateRegistry.secretName }}
{{- end -}}
{{- end -}}
{{- define "elasticsearch.master.roles" -}}
{{- range $.Values.master.roles -}}
{{ . }},
{{- end -}}
{{- end -}}

{{- define "elasticsearch.data.roles" -}}
{{- range $.Values.data.roles -}}
{{ . }},
{{- end -}}
{{- end -}}

{{- define "elasticsearch.client.roles" -}}
{{- range $.Values.client.roles -}}
{{ . }},
{{- end -}}
{{- end -}}

{{- define "curator.indexPattern" -}}
{{ if and .Values.global.logging.loggingSidecar.enabled .Values.global.logging.loggingSidecar.indexPattern }}
{{- .Values.global.logging.loggingSidecar.indexPattern | squote }}
{{ else }}
{{- .Values.curator.age.timestring | squote}}
{{- end -}}
{{- end -}}

{{/*
Return exporter podSecurityContext, omitting fsGroup,runAsGroup and runAsUser fields on OpenShift Based Installation.
Uses .Values.exporter.podSecurityContext as its own base (not the chart-wide .Values.podSecurityContext),
so it deliberately does not use platform.podSecurityContext, whose merge would layer the chart base underneath.
*/}}
{{- define "elasticsearch.exporter.podSecurityContext" -}}
{{- if .Values.global.openshift.enabled }}
{{- omit .Values.exporter.podSecurityContext "fsGroup" "runAsGroup" "runAsUser" | toYaml }}
{{- else }}
{{- toYaml .Values.exporter.podSecurityContext }}
{{- end -}}
{{- end }}

{{- define "elasticsearch.ingressurl" -}}
{{ if and (eq .Values.global.plane.mode "data") .Values.global.plane.domainPrefix -}}
elasticsearch.{{ .Values.global.plane.domainPrefix }}.{{ .Values.global.baseDomain }}
{{- else -}}
elasticsearch.{{ .Values.global.baseDomain }}
{{- end -}}
{{- end -}}

{{/*
NetworkPolicy ingress peers allowed to reach the ES nginx auth proxy (<release>-elasticsearch-nginx)
from the platform's ingress layer, so the public ES Ingress/VirtualService can route to it (APC-2206).

This is the ONLY ES policy that admits an ingress controller. The ES client policy must not: external
traffic has to go through the proxy, which authenticates every request with Houston and scopes it
to the caller's indices, never straight to Elasticsearch (which runs with xpack security off).

Behaviour, in order:
  * global.authSidecar.enabled (the auth sidecar / OpenShift or Istio gateway model): the ingress is
    not one of our controllers, so admit the OpenShift ingress policy-group namespaces, plus any
    namespaces listed in global.authSidecar.ingressAllowedNamespaces.
  * otherwise: admit the data plane's own ingress controller pods of this release (component
    "dp-ingress-controller").

Only the data plane publishes this host. Unified and control plane installs read ES in-cluster, so
their Ingress, VirtualService and this peer are not rendered at all (the caller wraps the include in a
data-mode check).

Renders a list of NetworkPolicyPeer items, to be spliced into a `from:` list.
*/}}
{{- define "nginx-es.ingressControllerPeers" -}}
{{- if .Values.global.authSidecar.enabled }}
- namespaceSelector:
    matchLabels:
      network.openshift.io/policy-group: ingress
{{- if .Values.global.authSidecar.ingressAllowedNamespaces }}
- namespaceSelector:
    matchExpressions:
    - key: kubernetes.io/metadata.name
      operator: In
      values: {{ .Values.global.authSidecar.ingressAllowedNamespaces | toJson }}
{{- end }}
{{- else }}
- podSelector:
    matchLabels:
      tier: nginx
      component: dp-ingress-controller
      release: {{ .Release.Name }}
{{- end }}
{{- end -}}
