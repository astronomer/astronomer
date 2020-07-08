#!/usr/bin/env bats

load ../config
load ../helpers/semver

@test "Terraform" {
  run terraform version --client --short
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  version=$(echo "$output" | head -n 1 | awk '{ print $2 }' | tr -d 'v')

  run semver_compare $version "$TERRAFORM_MIN"
  if [[ "$output" -eq -1 ]]; then
    echo "Terraform version '$version' does not meet minimum of '$TERRAFORM_MIN'"
  fi
  [ "$output" -ne -1 ]
}

@test "Kubectl" {
  run kubectl version --client --short
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  version=$(echo "$output" | awk '{ print $3 }' | tr -d 'v')

  run semver_compare $version "$KUBECTL_MIN"
  if [[ "$output" -eq -1 ]]; then
    echo "Kubectl version '$version' does not meet minimum of '$KUBECTL_MIN'"
  fi
  [ "$output" -ne -1 ]
}

@test "Helm" {
  run helm version --client --short
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  version=$(echo "$output" | sed -e 's/Client: //'| tr '+' ' ' | awk '{ print $1 }' | tr -d 'v')

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

