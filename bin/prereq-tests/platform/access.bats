#!/usr/bin/env bats

load ../config

@test "Astronomer UI" {
  DOMAIN="https://app.$ASTRONOMER_BASEDOMAIN"
  run curl -v "$DOMAIN"

  if [ "$status" -ne 0 ]; then
    echo "# Could not reach UI"
    echo "$output"
  fi
  [ "$status" -eq 0 ]
}

