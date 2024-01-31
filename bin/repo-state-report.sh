#!/usr/bin/env bash

GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
GIT_ORIGIN=$(git config --get remote.origin.url)
GIT_SHA=$(git rev-parse HEAD)$(if [[ -n "$(git status --porcelain)" ]] ; then echo " DIRTY" ; fi)
BUILD_DATE_ISO8601=$(date +%FT%T%z)

output=(
    "Build time:  ${BUILD_DATE_ISO8601}"
    "Git repo:    ${GIT_ORIGIN}"
    "Git branch:  ${GIT_BRANCH}"
    "Git SHA:     ${GIT_SHA}"
)

[[ -n "${CIRCLE_BUILD_URL}" ]] && output+=( "CircleCI Build URL:       ${CIRCLE_BUILD_URL}" )
[[ -n "${CIRCLE_BUILD_NUM}" ]] && output+=( "CircleCI Build Number:    ${CIRCLE_BUILD_NUM}" )
[[ -n "${CIRCLE_REPOSITORY_URL}" ]] && output+=( "CircleCI Repository URL:  ${CIRCLE_REPOSITORY_URL}" )
[[ -n "${CIRCLE_SHA1}" ]] && output+=( "CircleCI SHA1:            ${CIRCLE_SHA1}" )
[[ -n "${CIRCLE_WORKFLOW_ID}" ]] && output+=( "CircleCI Workflow ID:     ${CIRCLE_WORKFLOW_ID}" )
[[ -n "${CIRCLE_JOB}" ]] && output+=( "CircleCI Job:             ${CIRCLE_JOB}" )

for item in "${output[@]}" ; do
    echo "$item"
done
