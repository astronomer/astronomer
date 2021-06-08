{{/*
Generic Kubernetes apiVersion helpers

Add any definitions at the version they are introduced to the API. EG: do not use v1beta1 if v1 exists.
Delete definitions at the version they are deleted from the API.
Delete logic related to unsupported versions of kubernetes. EG: https://www.astronomer.io/docs/enterprise/v0.25/resources/version-compatibility-reference
*/}}

{{- define "apiVersion.DaemonSet" -}}
apps/v1
{{- end -}}

{{- define "apiVersion.Deployment" -}}
apps/v1
{{- end -}}

{{- define "apiVersion.Ingress" -}}
{{- if semverCompare "<1.19-0" .Capabilities.KubeVersion.Version -}}
networking.k8s.io/v1beta1
{{- else -}}
networking.k8s.io/v1
{{- end -}}
{{- end -}}

{{- define "apiVersion.NetworkPolicy" -}}
networking.k8s.io/v1
{{- end -}}

{{- define "apiVersion.PodSecurityPolicy" -}}
extensions/v1beta1
{{- end -}}

{{- define "apiVersion.PriorityClass" -}}
scheduling.k8s.io/v1
{{- end -}}

{{- define "apiVersion.rbac" -}}
rbac.authorization.k8s.io/v1
{{- end -}}

{{- define "apiVersion.batch" -}}
batch/v1
{{- end -}}

{{- define "apiVersion.batch.cronjob" -}}
{{- if semverCompare ">=1.21-0" .Capabilities.KubeVersion.Version -}}
batch/v1
{{- else -}}
batch/v1beta1
{{- end -}}

{{- define "apiVersion.istio.networking" -}}
networking.istio.io/v1alpha3
{{- end -}}
