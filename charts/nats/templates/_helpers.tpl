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
