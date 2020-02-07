#!/usr/bin/env bats

load ../config

@test "Check for gcloud cli" {
  run gcloud --version
  [ "$status" -eq 0 ]
}

