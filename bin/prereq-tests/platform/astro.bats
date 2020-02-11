#!/usr/bin/env bats

load ../config

@test "CLI Install" {
  run kubectl get --namespace $NAMESPACE pods --no-headers -l tier=astronomer,component=cli-install
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

@test "Prisma" {
  run kubectl get --namespace $NAMESPACE pods --no-headers -l tier=astronomer,component=prisma
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

@test "Registry" {
  run kubectl get --namespace $NAMESPACE pods --no-headers -l tier=astronomer,component=registry
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

@test "Houston" {
  run kubectl get --namespace $NAMESPACE pods --no-headers -l tier=astronomer,component=houston
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

@test "Commander" {
  run kubectl get --namespace $NAMESPACE pods --no-headers -l tier=astronomer,component=commander
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

@test "Orbit" {
  run kubectl get --namespace $NAMESPACE pods --no-headers -l tier=astronomer,component=orbit
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

