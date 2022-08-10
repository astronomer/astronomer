{{ define "pgbouncer_image" -}}
{{ printf "%s:%s" .Values.image.repository .Values.image.tag }}
{{- end }}

{{ define "pgbouncer_host" -}}
{{ printf "%s-pgbouncer" .Release.Name }}
{{- end }}

{{ define "pgbouncer_config_secret" -}}
{{ printf "%s-pgbouncer-config" .Release.Name }}
{{- end }}

{{ define "pgbouncer_stats_secret" -}}
{{ .Release.Name }}-pgbouncer-stats
{{- end }}
