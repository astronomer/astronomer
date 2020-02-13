#!/usr/bin/env bats

load ../config
load ../helpers/semver

@test "AWS CLI" {
  run aws --version
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]
  version=$(echo "$output" | tr '/' ' ' | awk '{ print $2 }')

  run semver_compare $version "$AWSCLI_MIN"
  if [[ "$output" -eq -1 ]]; then
    echo "AWS CLI version '$version' does not meet minimum of '$AWSCLI_MIN'"
  fi
  [ "$output" -ne -1 ]
}

@test "Valid AWS credentials" {
  run aws sts get-caller-identity
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]
}

@test "AWS iam authenticator" {
  run aws-iam-authenticator version --short
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]
  version=$(echo "${lines[0]}" | awk '{ print $2 }' | tr -d 'v')

  run semver_compare $version "$AWSIAM_MIN"
  if [[ "$output" -eq -1 ]]; then
    echo "AWS IAM Authenticator version '$version' does not meet minimum of '$AWSIAM_MIN'"
  fi
  [ "$output" -ne -1 ]
}

