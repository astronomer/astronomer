#!/usr/bin/env bats

load ../config

@test "Check for DB vars set" {

  if [ "$DB_HOST" == "" ]; then
    echo "DB_HOST not set in config.bash"
  fi
  [ "$DB_HOST" != "" ]


  if [ "$DB_PORT" == "" ]; then
    echo "DB_PORT not set in config.bash"
  fi
  [ "$DB_PORT" != "" ]


  if [ "$DB_USER" == "" ]; then
    echo "DB_USER not set in config.bash"
  fi
  [ "$DB_USER" != "" ]


  if [ "$DB_PASS" == "" ]; then
    echo "DB_PASS not set in config.bash"
  fi
  [ "$DB_PASS" != "" ]

}


