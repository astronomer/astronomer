#!/usr/bin/env bats

load ../config
load ../helpers/semver

@test "Docker" {
  # check in path
  run which docker
  if [ "$status" -ne 0 ]; then
    echo "Docker tool missing"
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  # check command can run
  run docker version
  if [ "$status" -ne 0 ]; then
    echo "Docker tool error"
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  # Check version for minimum
  version=$(echo "${lines[1]}" | awk '{ print $2 }')
  run semver_compare $version "$DOCKER_MIN"
  if [[ "$output" -eq -1 ]]; then
    echo "Docker version '$version' does not meet minimum of '$DOCKER_MIN'"
  fi
  [ "$output" -ne -1 ]
}

@test "Astronomer CLI" {
  run astro version
  if [ "$status" -ne 0 ]; then
    echo "Astro CLI missing"
  fi
  [ "$status" -eq 0 ]

  version=$(echo "${lines[0]}" | awk '{ print $4 }')

  run semver_compare $version "$ASTRONOMER_VERSION"
  if [[ "$output" -ne -0 ]]; then
    echo "Astro CLI version '$version' does not match configured version '$ASTRONOMER_VERSION'"
  fi
  [ "$output" -eq -0 ]
}
