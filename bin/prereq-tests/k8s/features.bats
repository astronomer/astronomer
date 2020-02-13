#!/usr/bin/env bats

load ../config

@test "Cluster RBAC" {
  run bash -c "kubectl api-resources | grep rbac.authorization.k8s.io"

  if [ "$status" -ne 0 ]; then
    echo "# No RBAC resources found"
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  count=$(echo "$output" | wc -l )

  if [ "$status" -ne 0 ]; then
    echo "# Incorrect RBAC resources found"
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  if [ "$count" != "4" ]; then
    echo "# Incorrect RBAC resources found"
    echo "$result"
  fi
  [ "$count" = "4" ]
}

@test "Default Storage Class" {
  run kubectl get storageclass
  if [ "$status" -ne 0 ]; then
    echo "# No Storage Classes found"
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  result=$output
  name=$(echo "$results" | grep default | awk '{ print $1 }')
  if [ "$status" -ne 0 ]; then
    echo "# No Default Storage Classes found"
    echo "$result"
  fi
  [ "$status" -eq 0 ]
}

