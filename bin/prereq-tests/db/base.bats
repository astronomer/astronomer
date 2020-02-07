#!/usr/bin/env bats

load ../config

@test "Check for DB vars set" {
  [ "$DB_HOST" != "" ]
  [ "$DB_PORT" != "" ]
  [ "$DB_USER" != "" ]
  [ "$DB_PASS" != "" ]
}


