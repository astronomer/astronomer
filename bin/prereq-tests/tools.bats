#!/usr/bin/env bats

@test "Check for Helm CLI" {
  run helm version --client --short
  [ "$status" -eq 0 ]
}

@test "Check for Kubectl" {
  run kubectl version --client --short
  [ "$status" -eq 0 ]
}

