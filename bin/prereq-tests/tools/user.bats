#!/usr/bin/env bats

load ../helpers/semver

@test "Docker" {
  run docker version
  [ "$status" -eq 0 ]

  # version=$(echo "$output" | awk '{ print $2 }' | tr -d 'v')

  # run semver_compare $version "0.12.0"
  # [ "$output" -ne -1 ]
}

@test "Astronomer CLI" {
  run astro version
  [ "$status" -eq 0 ]
}
