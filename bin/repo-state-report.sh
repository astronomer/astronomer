#!/usr/bin/env bash

GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
GIT_ORIGIN=$(git config --get remote.origin.url)
GIT_SHA=$(git rev-parse HEAD)$(if [[ -n "$(git status --porcelain)" ]] ; then echo " DIRTY" ; fi)
BUILD_DATE_ISO8601=$(date +%FT%T%z)

cat <<EOF
Git repo:   ${GIT_ORIGIN}
Git branch: ${GIT_BRANCH}
Git SHA:    ${GIT_SHA}
Build time: ${BUILD_DATE_ISO8601}
EOF
