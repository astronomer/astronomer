#!/bin/usr/env bash

NAMESPACE="astronomer"
ASTRONOMER_VERSION="0.11.0"
ASTRONOMER_BASEDOMAIN="staging.astronomer.io"

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

source $DIR/helpers/versions/astronomer-$ASTRONOMER_VERSION.bash

DB_HOST="postgres"
DB_PORT="5432"
DB_USER=""
DB_PASS=""
