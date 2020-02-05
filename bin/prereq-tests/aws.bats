#!/usr/bin/env bats

@test "Check for AWS CLI" {
  run aws --version
  [ "$status" -eq 0 ]
}
