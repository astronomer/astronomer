#!/usr/bin/env bats

load ../config

@test "Bootstrap Secret" {
  run kubectl get --namespace $NAMESPACE secret astronomer-bootstrap
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]
}

@test "TLS Secret" {
  run kubectl get --namespace $NAMESPACE secret astronomer-tls
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]
}

