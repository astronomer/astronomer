{{/* Generic Kubernetes apiVersion helpers */}}

{{- define "apiVersion.DaemonSet" -}}
apps/v1
{{- end -}}

{{- define "apiVersion.Deployment" -}}
apps/v1
{{- end -}}

{{- define "apiVersion.Deployment.16" -}}
{{- if semverCompare "^1.16-0" .Capabilities.KubeVersion.Version }}
apps/v1
{{- else }}
apps/v1beta2
{{- end }}
{{- end -}}

{{- define "apiVersion.Ingress" -}}
{{- if semverCompare "^1.14-0" .Capabilities.KubeVersion.Version -}}
networking.k8s.io/v1beta1
{{- else -}}
extensions/v1beta1
{{- end -}}
{{- end -}}

{{- define "apiVersion.NetworkPolicy" -}}
networking.k8s.io/v1
{{- end -}}

{{- define "apiVersion.PodSecurityPolicy" -}}
{{- if semverCompare "^1.10-0" .Capabilities.KubeVersion.Version -}}
policy/v1beta1
{{- else -}}
extensions/v1beta1
{{- end -}}
{{- end -}}

{{- define "apiVersion.PriorityClass" -}}
{{- if semverCompare "^1.14-0" .Capabilities.KubeVersion.Version -}}
scheduling.k8s.io/v1
{{- else -}}
scheduling.k8s.io/v1beta1
{{- end -}}
{{- end -}}

{{- define "apiVersion.rbac.v1beta2" -}}
{{- if semverCompare "^1.16-0" .Capabilities.KubeVersion.Version -}}
rbac.authorization.k8s.io/v1
{{- else -}}
use something more specific
{{- end -}}
{{- end -}}

{{- define "apiVersion.rbac.v1beta1" -}}
{{- if semverCompare "^1.16-0" .Capabilities.KubeVersion.Version -}}
rbac.authorization.k8s.io/v1
{{- else -}}
rbac.authorization.k8s.io/v1beta1
{{- end -}}
{{- end -}}

{{- define "apiVersion.batch.v1beta1" -}}
{{- if semverCompare "^1.16-0" .Capabilities.KubeVersion.Version -}}
batch/v1
{{- else -}}
batch/v1beta1
{{- end -}}
{{- end -}}

{{- define "apiVersion.istio.networking" -}}
networking.istio.io/v1alpha3
{{- end -}}
