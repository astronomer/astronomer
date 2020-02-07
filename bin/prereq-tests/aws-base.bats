#!/usr/bin/env bats

load semver

@test "AWS CLI" {
  run aws --version
  [ "$status" -eq 0 ]
  result=$output
  version=$(echo "$result" | tr '/' ' ' | awk '{ print $2 }')

  run semver_compare $version "1.0.0"
  [ "$output" -ne -1 ]
}

@test "Valid AWS credentials" {
  run aws sts get-caller-identity
  [ "$status" -eq 0 ]
}

