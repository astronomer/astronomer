#!/usr/bin/env bats

load ../config
load ../helpers/semver

@test "Terraform" {
  run terraform version --client --short
  [ "$status" -eq 0 ]

  version=$(echo "$output" | awk '{ print $2 }' | tr -d 'v')

  run semver_compare $version "$TERRAFORM_MIN"
  [ "$output" -ne -1 ]
}

@test "Kubectl" {
  run kubectl version --client --short
  [ "$status" -eq 0 ]

  version=$(echo "$output" | awk '{ print $3 }' | tr -d 'v')

  run semver_compare $version "$KUBECTL_MIN"
  [ "$output" -ne -1 ]
}

@test "Helm" {
  run helm version --client --short
  [ "$status" -eq 0 ]

  version=$(echo "$output" | tr '+' ' ' | awk '{ print $2 }' | tr -d 'v')

  run semver_compare $version "$HELM_MIN"
  [ "$output" -ne -1 ]

  run semver_compare $version "$HELM_LESSTHAN"
  [ "$output" -eq -1 ]
}

