#!/usr/bin/env bats

load ../config
load ../helpers/semver

@test "Docker" {
  run docker version
  [ "$status" -eq 0 ]

  version=$(echo "${lines[1]}" | awk '{ print $2 }')

  run semver_compare $version "18.09.0"
  [ "$output" -ne -1 ]
}

@test "Astronomer CLI" {
  run astro version
  [ "$status" -eq 0 ]

  version=$(echo "${lines[0]}" | awk '{ print $4 }')

  run semver_compare $version "$ASTRONOMER_VERSION"
  [ "$output" -ne -1 ]
}
