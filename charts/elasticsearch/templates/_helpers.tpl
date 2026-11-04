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

{{/*
The timestring curator uses for its age filter, unquoted.

Two sources of truth, in priority order:
  1. global.logging.loggingSidecar.indexPattern -- the customer-facing knob, which also
     drives the index name the vector logging sidecar writes to (via Houston).
  2. curator.age.timestring -- the subchart default, used when the sidecar is off.

Kept separate from "curator.indexPattern" so the granularity helpers below can inspect
the raw value without having to strip quotes.
*/}}
{{- define "curator.age.timestringRaw" -}}
{{- if and .Values.global.logging.loggingSidecar.enabled .Values.global.logging.loggingSidecar.indexPattern -}}
{{- .Values.global.logging.loggingSidecar.indexPattern -}}
{{- else -}}
{{- .Values.curator.age.timestring -}}
{{- end -}}
{{- end -}}

{{- define "curator.indexPattern" -}}
{{- include "curator.age.timestringRaw" . | squote -}}
{{- end -}}

{{/*
The finest time unit actually present in the effective timestring.

Curator's age filter with "source: name" parses the index name through
strptime(timestring) and treats the result as the index's age date. strptime anchors
missing components to their lowest value, so strptime("2026.04", "%Y.%m") yields
2026-04-01. Comparing that against a *day*-granularity retention means the current
month's index looks older than "10 days" from the 11th onward and gets deleted, even
though it is the index currently being written to. See PINF-578.

Deriving the unit from the timestring keeps the two halves of the filter consistent:
  %Y.%m.%d -> days   (chart default)
  %Y.%m    -> months
  %Y       -> years

Ordered finest-first so the most specific component present wins. Every unit curator
accepts is covered on purpose: "curator.age.validate" compares an operator's explicit
unit against this result, so a missing directive here would turn a legitimate config
(e.g. weekly %Y.%W indices with unit: weeks) into a spurious template failure.
Falls back to days -- the historical default -- for a timestring with no recognised
directive.
*/}}
{{- define "curator.age.derivedUnit" -}}
{{- $timestring := include "curator.age.timestringRaw" . -}}
{{- if regexMatch "%S" $timestring -}}seconds
{{- else if regexMatch "%M" $timestring -}}minutes
{{- else if regexMatch "%H" $timestring -}}hours
{{- else if regexMatch "%[dj]" $timestring -}}days
{{- else if regexMatch "%[WU]" $timestring -}}weeks
{{- else if regexMatch "%m" $timestring -}}months
{{- else if regexMatch "%[Yy]" $timestring -}}years
{{- else -}}days
{{- end -}}
{{- end -}}

{{/*
The unit curator's age filter actually gets.

An explicitly set curator.age.unit always wins -- operators who deliberately pick a
unit keep control, and "curator.age.validate" below is what stops them picking a unit
that would delete live indices. When curator.age.unit is null (the chart default) the
unit is derived from the timestring so the single customer-facing indexPattern knob
stays internally consistent.
*/}}
{{- define "curator.age.unit" -}}
{{- if .Values.curator.age.unit -}}
{{- .Values.curator.age.unit -}}
{{- else -}}
{{- include "curator.age.derivedUnit" . -}}
{{- end -}}
{{- end -}}

{{/*
Reject a curator.age.unit that is finer than the index-name granularity.

Included from the curator ConfigMap, so it only runs when curator is actually going to
delete indices. Emits nothing on success.

Curator's age filter with "source: name" parses the index name through
strptime(timestring), which anchors missing components to their lowest value:
strptime("2026.04", "%Y.%m") is 2026-04-01. A retention unit finer than the index-name
granularity therefore makes the index currently being written to look expired -- from
the 11th of the month onward for the default 10-day window -- and curator deletes it.
No error, no warning: curator is doing exactly what it was told. Vector recreates the
index on its next bulk write, so writes keep succeeding and only history disappears.
See PINF-578.

Leaving curator.age.unit unset lets "curator.age.unit" derive a consistent unit, so
this only fires when an explicit unit contradicts the timestring -- always data loss
waiting to happen rather than a preference worth respecting.
*/}}
{{- define "curator.age.validate" -}}
{{- if .Values.curator.age.unit -}}
{{- $configured := .Values.curator.age.unit | toString -}}
{{- $derived := include "curator.age.derivedUnit" . -}}
{{- $timestring := include "curator.age.timestringRaw" . -}}
{{- $ranks := dict "seconds" 1 "minutes" 2 "hours" 3 "days" 4 "weeks" 5 "months" 6 "years" 7 -}}
{{- if not (hasKey $ranks $configured) -}}
{{- fail (printf "elasticsearch.curator.age.unit is %q, which curator does not accept; valid units are seconds, minutes, hours, days, weeks, months, years (or leave it unset to derive it from the index timestring %q)" $configured $timestring) -}}
{{- end -}}
{{- if lt (int (index $ranks $configured)) (int (index $ranks $derived)) -}}
{{- fail (printf "elasticsearch.curator.age.unit is %q but the curator index timestring is %q, whose finest component is %q. A retention unit finer than the index-name granularity makes curator delete the index it is still writing to, destroying every log written since the last curator run (PINF-578). Fix this by either unsetting elasticsearch.curator.age.unit so it is derived as %q, setting it to %q or coarser, or switching to a finer index pattern such as \"%%Y.%%m.%%d\"." $configured $timestring $derived $derived $derived) -}}
{{- end -}}
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
