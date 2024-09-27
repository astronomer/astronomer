#!/usr/bin/env bash
# Build the astronomer helm chart based off of the current git branch
#
# https://circleci.com/docs/2.0/env-vars/#built-in-environment-variables

set -x
set -e

TEMPDIR="${TEMPDIR:-/tmp/astro-temp}"
git_root="$(git rev-parse --show-toplevel)"

rm -rf "${TEMPDIR}/astronomer" || true
mkdir -p "${TEMPDIR}"
cp -R "${git_root}/" "${TEMPDIR}/astronomer/"
find "${TEMPDIR}/astronomer/charts" -name requirements.yaml -execdir helm dep update \;

helm package "${TEMPDIR}/astronomer"
