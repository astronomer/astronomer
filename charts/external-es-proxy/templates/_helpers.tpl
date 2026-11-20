{{/*
Expand the name of the chart.
*/}}
{{- define "external-es-proxy.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "external-es-proxy.fullname" -}}
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
Create chart name and version as used by the chart label.
*/}}
{{- define "external-es-proxy.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "external-es-proxy.labels" -}}
helm.sh/chart: {{ include "external-es-proxy.chart" . }}
{{ include "external-es-proxy.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "external-es-proxy.selectorLabels" -}}
app.kubernetes.io/name: {{ include "external-es-proxy.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "external-es-proxy.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "external-es-proxy.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}


{{/*
Option to add trust certs when privateCA or self signed certs are used
with hosted elastic search. By defaults it is off when trustCaCerts are
provided it will use that certs to trust the connection
*/}}

{{- define "external-es-proxy-trustcerts" -}}
{{- if .Values.global.customLogging.trustCaCerts }}
{{- $secret_name := .Values.global.customLogging.trustCaCerts }}
proxy_ssl_trusted_certificate /etc/ssl/certs/{{ $secret_name }}.pem;
proxy_ssl_verify on;
proxy_ssl_verify_depth 2;
proxy_ssl_session_reuse on;
{{- else }}
proxy_ssl_verify off;
{{- end }}
{{- end }}

{{/*
Return the proper Docker Image Registry Secret Names
*/}}
{{- define "external-es-proxy.imagePullSecrets" -}}
{{- if and .Values.global.privateRegistry.enabled .Values.global.privateRegistry.secretName }}
imagePullSecrets:
  - name: {{ .Values.global.privateRegistry.secretName }}
{{- end -}}
{{- end -}}


{{ define "esproxy.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-openresty:{{ .Values.images.esproxy.tag }}
{{- else -}}
{{ .Values.images.esproxy.repository}}:{{ .Values.images.esproxy.tag }}
{{- end }}
{{- end }}


{{ define "awsesproxy.image" -}}
{{- if .Values.global.privateRegistry.enabled -}}
{{ .Values.global.privateRegistry.repository }}/ap-awsesproxy:{{ .Values.images.awsproxy.tag }}
{{- else -}}
{{ .Values.images.awsproxy.repository }}:{{ .Values.images.awsproxy.tag }}
{{- end }}
{{- end }}


{{/*
"true" when the customer's Elasticsearch is reached through the AWS signing proxy (the `awsproxy` sidecar container on
localhost:<service.awsproxy>), which any of the three AWS authentication options turns on: a static key Secret
(awsSecretName), IRSA (awsServiceAccountAnnotation) or kube2iam (awsIAMRole). Empty otherwise, when requests go to the
customer's host directly with the credential added by setenv.lua. Every place that has to agree on this (the sidecar in
the Deployment, where nginx forwards, the upstream) uses this one definition so they cannot drift apart.
*/}}
{{- define "external-es-proxy-uses-aws" -}}
{{- $csc := .Values.global.customLogging -}}
{{- if or $csc.awsSecretName $csc.awsServiceAccountAnnotation $csc.awsIAMRole -}}
true
{{- end -}}
{{- end }}

{{/*
Switches the elasticsearch configuratiob based on customLogging
when aws managed elastic search is confired awsesproxy settings is required
to authenticate with aws managed elastic search or opensearch
*/}}

{{- define "external-es-proxy-nginx-location-common" -}}
{{- if eq (include "external-es-proxy-uses-aws" .) "true" }}
proxy_pass http://localhost:{{ .Values.service.awsproxy }};
{{- else }}
access_by_lua_file /usr/local/openresty/nginx/conf/setenv.lua;
proxy_pass {{.Values.global.customLogging.scheme}}://{{.Values.global.customLogging.host}}:{{.Values.global.customLogging.port}};
{{- include "external-es-proxy-trustcerts" . }}
{{- end }}
{{- end }}

{{/*
The server the authenticated port (securehttp) forwards to: the signing proxy when one is configured, else the
customer's Elasticsearch. It is an nginx `upstream` because the scoped locations below build the request URI from a
variable ($es_scope), and nginx resolves a proxy_pass host at request time (needing a resolver) unless it names an
upstream group.
*/}}
{{- define "external-es-proxy-upstream-server" -}}
{{- if eq (include "external-es-proxy-uses-aws" .) "true" -}}
localhost:{{ .Values.service.awsproxy }}
{{- else -}}
{{ .Values.global.customLogging.host }}:{{ include "external-es-proxy-customer-port" . }}
{{- end -}}
{{- end }}

{{/*
The customer Elasticsearch port. A bare `host:` is not valid in an `upstream`, so fall back to the scheme's default
when customLogging.port is unset.
*/}}
{{- define "external-es-proxy-customer-port" -}}
{{- $csc := .Values.global.customLogging -}}
{{- if $csc.port -}}
{{ $csc.port }}
{{- else if eq (toString $csc.scheme) "http" -}}
80
{{- else -}}
443
{{- end -}}
{{- end }}

{{/*
A location body for the authenticated port: forward to the one index pattern Houston's /v2/elasticsearch answered with
(`$es_scope`), never to a path the client chose. Takes a dict with `ctx` (the root context) and `op` (_search, _count
or _bulk). Same behaviour as the ES nginx proxy, plus what the single-server external proxy needs to keep working
through an `upstream`: the Host header and the TLS name must still be the customer's host, not the group name.
*/}}
{{- define "external-es-proxy-nginx-scoped-location" -}}
{{- $ctx := .ctx -}}
{{- $csc := $ctx.Values.global.customLogging -}}
{{- if eq (include "external-es-proxy-uses-aws" $ctx) "true" }}
proxy_set_header Host localhost:{{ $ctx.Values.service.awsproxy }};
proxy_pass http://external_es/{{ include "logging.indexNamePrefix" $ctx }}.$es_scope.*/{{ .op }}$is_args$args;
{{- else }}
access_by_lua_file /usr/local/openresty/nginx/conf/setenv.lua;
proxy_set_header Host {{ $csc.host }}:{{ include "external-es-proxy-customer-port" $ctx }};
proxy_ssl_name {{ $csc.host }};
proxy_pass {{ $csc.scheme }}://external_es/{{ include "logging.indexNamePrefix" $ctx }}.$es_scope.*/{{ .op }}$is_args$args;
{{- include "external-es-proxy-trustcerts" $ctx }}
{{- end }}
{{- end }}

{{- define "es-proxy.url" -}}
{{- if .Values.global.plane.domainPrefix -}}
elasticsearch.{{ .Values.global.plane.domainPrefix }}.{{ .Values.global.baseDomain }}
{{- else -}}
elasticsearch.{{ .Values.global.baseDomain }}
{{- end -}}
{{- end -}}
