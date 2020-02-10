#!/usr/bin/env bats

load ../config

@test "Manage Everything" {
  run kubectl auth can-i '*' '*' --all-namespaces
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]
  [ "$output" = "yes" ]
}

