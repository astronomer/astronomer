#!/usr/bin/env bats

load ../helpers/semver

@test "API access" {
  run kubectl version --short
  [ "$status" -eq 0 ]

  version=$(echo "$output" | tail -n 1 | tr '-' ' ' | awk '{ print $3 }' | tr -d 'v')

  run semver_compare $version "1.12.0"
  [ "$output" -ne -1 ]

  run semver_compare $version "1.18.0"
  [ "$output" -eq -1 ]
}

@test "Tiller" {
  run helm version --client --short
  [ "$status" -eq 0 ]

  version=$(echo "$output" | tr '+' ' ' | awk '{ print $2 }' | tr -d 'v')

  run semver_compare $version "2.14.0"
  [ "$output" -ne -1 ]

  run semver_compare $version "3.0.0"
  [ "$output" -eq -1 ]
}


