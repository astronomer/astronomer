#!/usr/bin/env bats

load ../config

@test "Check for DB vars set" {
  echo "DB_HOST = '$DB_HOST'"
  [ "$DB_HOST" != "" ]

  echo "DB_PORT = '$DB_PORT'"
  [ "$DB_PORT" != "" ]

  echo "DB_USER = '$DB_USER'"
  [ "$DB_USER" != "" ]

  echo "DB_PASS = '$DB_PASS'"
  [ "$DB_PASS" != "" ]
}


