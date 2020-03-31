#!/usr/bin/env bats

load ../config

@test "Check for gcloud cli" {
  run gcloud --version
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]
}

