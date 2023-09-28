#!/usr/bin/env bash

echo "
Description:
  This script is PoC of how can you migrate
  give airflow deployment to another DB.

  This script assumes:

  Assumption 1: user is responsible of making any networking connectivity between
  PG server 2 and airflow deployment.

  Assumption 2: you have access to both DB instanceses so you can run pg_dump pg_restore

  Assumption 3:  Make sure you pg_dump/pg_restore versions matched
"


export PATH="/usr/local/opt/postgresql@11/bin:$PATH"
ASTRONOMER_AIRFLOW_CHART="astronomer-ee/airflow"
RELEASE_NAME="${1:-dynamical-nucleus-9402}"
AIRFLOW_DB_NAME="${RELEASE_NAME//\-/_}_airflow"
AIRFLOW_DB_DUMP_NAME="${AIRFLOW_DB_NAME}.tar"

AIRFLOW_DB_USERNAME=$AIRFLOW_DB_NAME
AIRFLOW_DB_PASSWORD=$(helm get values "${RELEASE_NAME}" -n astronomer-"${RELEASE_NAME}" -o json | jq -r '.airflow.data.metadataConnection.pass')
AIRFLOW_SCHEMA="airflow"
# AIRFLOW_DB_PASSWORD=""

CELERY_DB_USERNAME="${RELEASE_NAME//\-/_}_celery"
CELERY_DB_PASSWORD=$(helm get values "$RELEASE_NAME" -n astronomer-"$RELEASE_NAME}" -o json | jq -r '.airflow.data.resultBackendConnection.pass')
CELERY_SCHEMA="celery"

# CELERY_DB_PASSWORD=""

export DEST_DB_HOST_NAME=localhost
export DB_ADMIN_USER_NAME=postgres
export PGPASSWORD=postgres

echo "
Start migration of: $RELEASE_NAME

airflow db: $AIRFLOW_DB_NAME
airflow pass: $AIRFLOW_DB_PASSWORD
celery pass: $CELERY_DB_PASSWORD
"



rm -f ./"$AIRFLOW_DB_DUMP_NAME"

# F: selects the format of the dump
# t — export will be in tar format.

# create airflow & celery users
psql \
  -h ${DEST_DB_HOST_NAME} \
  -p 6543 \
  -U ${DB_ADMIN_USER_NAME} \
  -d postgres \
  -c \ "
CREATE USER ${AIRFLOW_DB_USERNAME} WITH LOGIN NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION CONNECTION LIMIT -1 ENCRYPTED PASSWORD '${AIRFLOW_DB_PASSWORD}';
GRANT ${AIRFLOW_DB_USERNAME} TO ${DB_ADMIN_USER_NAME}
CREATE SCHEMA IF NOT EXISTS ${AIRFLOW_SCHEMA} AUTHORIZATION ${AIRFLOW_DB_USERNAME};
ALTER DEFAULT PRIVILEGES IN SCHEMA ${AIRFLOW_SCHEMA} GRANT ALL PRIVILEGES ON TABLES TO ${AIRFLOW_DB_USERNAME};
ALTER DEFAULT PRIVILEGES IN SCHEMA ${AIRFLOW_SCHEMA} GRANT USAGE ON SEQUENCES TO ${AIRFLOW_DB_USERNAME};
GRANT USAGE ON SCHEMA ${AIRFLOW_SCHEMA} TO ${AIRFLOW_DB_USERNAME};
GRANT CREATE ON SCHEMA ${AIRFLOW_SCHEMA} TO ${AIRFLOW_DB_USERNAME};
GRANT ALL PRIVILEGES ON SCHEMA ${AIRFLOW_SCHEMA} TO ${AIRFLOW_DB_USERNAME};
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ${AIRFLOW_SCHEMA} TO ${AIRFLOW_DB_USERNAME};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA ${AIRFLOW_SCHEMA} TO ${AIRFLOW_DB_USERNAME};
REVOKE ${AIRFLOW_DB_USERNAME} TO ${DB_ADMIN_USER_NAME}
"

psql \
  -h ${DEST_DB_HOST_NAME} \
  -p 6543 \
  -U ${DB_ADMIN_USER_NAME} \
  -d postgres \
  -c \ "
CREATE USER ${CELERY_DB_USERNAME} WITH LOGIN NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION CONNECTION LIMIT -1 ENCRYPTED PASSWORD '${CELERY_DB_PASSWORD}';
GRANT ${CELERY_DB_USERNAME} TO ${DB_ADMIN_USER_NAME}
CREATE SCHEMA IF NOT EXISTS ${CELERY_SCHEMA} AUTHORIZATION ${CELERY_DB_USERNAME};
ALTER DEFAULT PRIVILEGES IN SCHEMA ${CELERY_SCHEMA} GRANT ALL PRIVILEGES ON TABLES TO ${CELERY_DB_USERNAME};
ALTER DEFAULT PRIVILEGES IN SCHEMA ${CELERY_SCHEMA} GRANT USAGE ON SEQUENCES TO ${CELERY_DB_USERNAME};
GRANT USAGE ON SCHEMA ${CELERY_SCHEMA} TO ${CELERY_DB_USERNAME};
GRANT CREATE ON SCHEMA ${CELERY_SCHEMA} TO ${CELERY_DB_USERNAME};
GRANT ALL PRIVILEGES ON SCHEMA ${CELERY_SCHEMA} TO ${CELERY_DB_USERNAME};
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ${CELERY_SCHEMA} TO ${CELERY_DB_USERNAME};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA ${CELERY_SCHEMA} TO ${CELERY_DB_USERNAME};
REVOKE ${CELERY_DB_USERNAME} TO ${DB_ADMIN_USER_NAME}
"


pg_dump -h localhost -p 5432 -d "$AIRFLOW_DB_NAME" -U postgres -F t > "$AIRFLOW_DB_DUMP_NAME"

pg_restore \
  --verbose \
  -h localhost \
  -p 6543 \
  -U postgres \
  -C -d postgres \
  "$AIRFLOW_DB_DUMP_NAME"
#
#
# Now we need to patch secrets
echo "
Start patching pgbouncer secrets
"


# Add astronomer helm repo
# helm repo add astronomer-ee https://helm.astronomer.io
# helm repo update astronomer-ee
# helm search repo astronomer-ee/airflow
# NAME                            CHART VERSION   APP VERSION     DESCRIPTION
# astronomer-ee/airflow           1.7.1           2.0.0           Helm chart to deploy the Astronomer Platform Ai...


helm upgrade \
  --version=1.7.0 \
  --set airflow.data.metadataConnection.host="astronomer-postgresql2.astronomer.svc.cluster.local" \
  --set airflow.data.resultBackendConnection.host="astronomer-postgresql2.astronomer.svc.cluster.local" \
  --reuse-values \
  --namespace astronomer-"$RELEASE_NAME" \
  "$RELEASE_NAME"
  "$ASTRONOMER_AIRFLOW_CHART"
