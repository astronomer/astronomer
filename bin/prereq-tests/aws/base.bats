#!/usr/bin/env bats

load ../helpers/semver

@test "AWS CLI" {
  run aws --version
  [ "$status" -eq 0 ]
  version=$(echo "$output" | tr '/' ' ' | awk '{ print $2 }')

  run semver_compare $version "1.0.0"
  [ "$output" -ne -1 ]
}

@test "Valid AWS credentials" {
  run aws sts get-caller-identity
  [ "$status" -eq 0 ]
}

@test "AWS iam authenticator" {
  run aws-iam-authenticator version --short
  [ "$status" -eq 0 ]
  version=$(echo "${lines[0]}" | awk '{ print $2 }' | tr -d 'v')

  run semver_compare $version "0.4.0"
  [ "$output" -ne -1 ]
}

