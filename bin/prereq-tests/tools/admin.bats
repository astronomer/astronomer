#!/usr/bin/env bats

load ../helpers/semver

@test "Terraform" {
  run terraform version --client --short
  [ "$status" -eq 0 ]

  version=$(echo "$output" | awk '{ print $2 }' | tr -d 'v')

  run semver_compare $version "0.12.0"
  [ "$output" -ne -1 ]
}

@test "Helm" {
  run helm version --client --short
  [ "$status" -eq 0 ]

  version=$(echo "$output" | tr '+' ' ' | awk '{ print $2 }' | tr -d 'v')

  run semver_compare $version "2.14.0"
  [ "$output" -ne -1 ]

  run semver_compare $version "3.0.0"
  [ "$output" -eq -1 ]
}

@test "Kubectl" {
  run kubectl version --client --short
  [ "$status" -eq 0 ]

  version=$(echo "$output" | awk '{ print $3 }' | tr -d 'v')

  run semver_compare $version "1.14.0"
  [ "$output" -ne -1 ]
}

