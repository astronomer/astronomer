#!/usr/bin/env bats

load ../config

@test "Wildcard DNS entry" {
  DOMAIN="*.$ASTRONOMER_BASEDOMAIN"
  run bash -c "dig '$DOMAIN' | grep -e '^${DOMAIN}'"

  if [ "$status" -ne 0 ]; then
    echo "# Wildcard DNS entry not found"
    echo "$output"
  fi
  [ "$status" -eq 0 ]
}

@test "Wildcard SSL Cert" {
  DOMAIN="https://app.$ASTRONOMER_BASEDOMAIN"
  run bash -c "curl -v '$DOMAIN' 2>&1 | grep 'SSL certificate verify ok'"

  if [ "$status" -ne 0 ]; then
    echo "# Wildcard DNS entry not found"
    echo "$output"
  fi
  [ "$status" -eq 0 ]
}

