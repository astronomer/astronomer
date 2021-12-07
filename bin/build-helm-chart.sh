#!/usr/bin/env bash
# Build the astronomer helm chart based off of the current git branch
#
# https://circleci.com/docs/2.0/env-vars/#built-in-environment-variables

set -x
set -e

TEMPDIR="${TEMPDIR:-/tmp/astro-temp}"
git_root="$(git rev-parse --show-toplevel)"

helm3 repo add kedacore https://kedacore.github.io/charts
rm -rf "${TEMPDIR}/astronomer" || true
mkdir -p "${TEMPDIR}"
cp -R "${git_root}/" "${TEMPDIR}/astronomer/"
find "${TEMPDIR}/astronomer/charts" -name requirements.yaml -execdir helm3 dep update \;

if [[ ! "${CIRCLE_BRANCH}" =~ release-[0-9]+\.[0-9]+ ]] ; then
  version=$(awk '$1 ~ /^version/ {printf "%s-build%s\n", $2, ENVIRON["CIRCLE_BUILD_NUM"]}' "${TEMPDIR}/astronomer/Chart.yaml")
  echo "Building helm chart for CIRCLE_BUILD_NUM $CIRCLE_BUILD_NUM version ${version}"
  sed -Ei "/(^version|appVersion): /s/^(version|appVersion): .*/\1: $version/" "${TEMPDIR}/astronomer/Chart.yaml" "${TEMPDIR}/astronomer/charts/astronomer/Chart.yaml"
  short_git_url=$(curl -sS -i https://git.io -F "url=https://github.com/astronomer/astronomer/commits/${CIRCLE_SHA1}" | awk '$1 == "Location:" {printf "%s", $2}')
  sed -i "s#^description: .*#description: $(date "+%FT%T%z") ${short_git_url} ${CIRCLE_BRANCH} ${CIRCLE_BUILD_URL}#" "${TEMPDIR}/astronomer/Chart.yaml"
fi

helm3 package "${TEMPDIR}/astronomer"
