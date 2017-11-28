#!/usr/bin/env bash
set -e

: ${AIRFLOW_HOME:="/usr/local/airflow"}

# Get path of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CMD=$2

# Wait for postgres then init the db.
if [[ -n $AIRFLOW__CORE__SQL_ALCHEMY_CONN  ]]; then
  if [[ $CMD == "webserver" ]] || [[ $CMD == "scheduler" ]]; then
    HOST=`echo $AIRFLOW__CORE__SQL_ALCHEMY_CONN | awk -F@ '{print $2}' | awk -F/ '{print $1}'`
    echo "Waiting for host: ${HOST}"
    ${DIR}/wait-for-it.sh ${HOST}

    echo "Initializing airflow postgres db..."
    airflow initdb

    echo "Ensuring database..."
    sleep 5
  fi
fi

if [[ -n $S3_ARTIFACT_PATH ]]; then
  echo "Refreshing AIRFLOW_HOME from s3"
  s3cmd get --force ${S3_ARTIFACT_PATH} latest.zip
  unzip -o latest.zip -d latest
  DAGS_DIR=$(find latest -type d -name dags)
  PLUGINS_DIR=$(find latest -type d -name plugins)
  rsync -a --ignore-existing ${DAGS_DIR} ${AIRFLOW_HOME}
  rsync -a --ignore-existing ${PLUGINS_DIR} ${AIRFLOW_HOME}
  rm -rf latest latest.zip
fi

# Run the `airflow` command.
exec $@
