{{- $metadata := .Files.Get "metadata.yaml" | fromYaml }}
{{- $versions := $metadata.test_k8s_versions }}
{{- $oldestMinor := regexReplaceAll "^(\\d+\\.\\d+).*" (index $versions 0) "${1}"}}
{{- $newestMinor := regexReplaceAll "^(\\d+\\.\\d+).*" (index $versions (sub (len $versions) 1)) "${1}"}}
{{- $err := (printf "\nThis version of Astronomer \"Software\" was tested on the following kubernetes versions:\n%s" ($versions | toYaml)) }}
{{ if and (semverCompare (printf "<%s" $oldestMinor) .Capabilities.KubeVersion.Version) (not .Values.forceIncompatibleKubernetes) -}}
    {{- $err := (printf "%s\n\nkubernetes version %s is unsupported because it is too old! You must upgrade your kubernetes version before continuing." $err .Capabilities.KubeVersion.Version) }}
    {{- $err := (printf "%s\n\nFor more details, refer to our documentation at https://docs.astronomer.io/software/release-lifecycle-policy" $err) }}
    {{- fail (printf "ABORT!\n%s" $err) }}
{{ else if and (semverCompare (printf ">%s" $newestMinor) .Capabilities.KubeVersion.Version) (not .Values.forceIncompatibleKubernetes) -}}
    {{- $err := (printf "%s\n\nkubernetes version %s is unsupported because it is too new! You must wait for a new version of Astronomer \"Software\" to be released that supports your version of kubernetes." $err .Capabilities.KubeVersion.Version) }}
    {{- $err := (printf "%s\n\nFor more details, refer to our documentation at https://docs.astronomer.io/software/release-lifecycle-policy" $err) }}
    {{- fail (printf "ABORT!\n%s" $err) }}
{{ end }}
