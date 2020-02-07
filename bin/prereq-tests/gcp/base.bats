#!/usr/bin/env bats

@test "Check for gcloud cli" {
  run gcloud --version
  [ "$status" -eq 0 ]
}

