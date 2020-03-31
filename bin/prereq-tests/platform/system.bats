#!/usr/bin/env bats

load ../config

@test "Logging" {
  run kubectl get --namespace $NAMESPACE pods --no-headers -l tier=logging
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  set +e
  badpods=$(echo "$output" | grep -v -e "Running" -e "Completed")
  set -e
  if [ "$badpods" != "" ]; then
    echo "$badpods"
  fi
  [ "$badpods" == "" ]
}

@test "Monitoring" {
  run kubectl get --namespace $NAMESPACE pods --no-headers -l tier=monitoring
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  set +e
  badpods=$(echo "$output" | grep -v -e "Running" -e "Completed")
  set -e
  if [ "$badpods" != "" ]; then
    echo "$badpods"
  fi
  [ "$badpods" == "" ]
}

@test "Ingress" {
  run kubectl get --namespace $NAMESPACE pods --no-headers -l tier=nginx
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  set +e
  badpods=$(echo "$output" | grep -v -e "Running" -e "Completed")
  set -e
  if [ "$badpods" != "" ]; then
    echo "$badpods"
  fi
  [ "$badpods" == "" ]
}

