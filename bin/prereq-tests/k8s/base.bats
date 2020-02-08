#!/usr/bin/env bats

load ../config
load ../helpers/semver

@test "API access" {
  run kubectl version --short
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  version=$(echo "$output" | tail -n 1 | tr '-' ' ' | awk '{ print $3 }' | tr -d 'v')

  run semver_compare $version "$KUBERNETES_MIN"
  if [[ "$output" -eq -1 ]]; then
    echo "Kubernetes version '$version' does not meet minimum of '$KUBERNETES_MIN'"
  fi
  [ "$output" -ne -1 ]

  run semver_compare $version "$KUBERNETES_LESSTHAN"
  if [[ "$output" -eq -1 ]]; then
    echo "Kubernetes version '$version' is not less than '$KUBERNETES_LESSTHAN'"
  fi
  [ "$output" -eq -1 ]
}

@test "Tiller" {
  run helm version --client --short
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  version=$(echo "$output" | tr '+' ' ' | awk '{ print $2 }' | tr -d 'v')

  run semver_compare $version "$HELM_MIN"
  if [[ "$output" -eq -1 ]]; then
    echo "Helm version '$version' does not meet minimum of '$HELM_MIN'"
  fi
  [ "$output" -ne -1 ]

  run semver_compare $version "$HELM_LESSTHAN"
  if [[ "$output" -ne -1 ]]; then
    echo "Helm 3 support is in progress. For now, use Helm 2."
  fi
  [ "$output" -eq -1 ]
}


