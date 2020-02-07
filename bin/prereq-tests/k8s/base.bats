#!/usr/bin/env bats

load ../config
load ../helpers/semver

@test "API access" {
  run kubectl version --short
  [ "$status" -eq 0 ]

  version=$(echo "$output" | tail -n 1 | tr '-' ' ' | awk '{ print $3 }' | tr -d 'v')

  run semver_compare $version "$KUBERNETES_MIN"
  [ "$output" -ne -1 ]

  run semver_compare $version "$KUBERNETES_LESSTHAN"
  [ "$output" -eq -1 ]
}

@test "Tiller" {
  run helm version --client --short
  [ "$status" -eq 0 ]

  version=$(echo "$output" | tr '+' ' ' | awk '{ print $2 }' | tr -d 'v')

  run semver_compare $version "$HELM_MIN"
  [ "$output" -ne -1 ]

  run semver_compare $version "$HELM_LESSTHAN"
  [ "$output" -eq -1 ]
}


