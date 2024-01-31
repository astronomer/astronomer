#!/usr/bin/env bash
# Build the astronomer helm chart based off of the current git branch
#
# https://circleci.com/docs/2.0/env-vars/#built-in-environment-variables

set -x
set -e

QA_FEATURE_RELEASE=${1:-false}
TEMPDIR="${TEMPDIR:-/tmp/astro-temp}"
git_root="$(git rev-parse --show-toplevel)"

rm -rf "${TEMPDIR}/astronomer" || true
mkdir -p "${TEMPDIR}"
cp -R "${git_root}/" "${TEMPDIR}/astronomer/"
find "${TEMPDIR}/astronomer/charts" -name requirements.yaml -execdir helm dep update \;

if [[ ! "${CIRCLE_BRANCH}" =~ release-[0-9]+\.[0-9]+ ]] ; then
  version=$(awk '$1 ~ /^version/ {printf "%s-build%s\n", $2, ENVIRON["CIRCLE_BUILD_NUM"]}' "${TEMPDIR}/astronomer/Chart.yaml")
  echo "Building helm chart for CIRCLE_BUILD_NUM $CIRCLE_BUILD_NUM version ${version}"
  sed -Ei='' "/(^version|appVersion): /s/^(version|appVersion): .*/\1: $version/" "${TEMPDIR}/astronomer/Chart.yaml" "${TEMPDIR}/astronomer/charts/astronomer/Chart.yaml"
  sed -i='' "s#^description: .*#description: $(date "+%FT%T%z") ${CIRCLE_BRANCH} ${CIRCLE_BUILD_URL} https://github.com/astronomer/astronomer/commits/${CIRCLE_SHA1}#" "${TEMPDIR}/astronomer/Chart.yaml"
  bin/repo-state-report.sh > "${TEMPDIR}/astronomer/repo_state.log"
elif [[ "${CIRCLE_BRANCH}" =~ release-[0-9]+\.[0-9]+ ]] ; then
  if [ "true" == "${QA_FEATURE_RELEASE}" ] ; then
    version=${CIRCLE_BRANCH/release-/""}-$(date -u +%Y%m%dT%H%M)-$(git rev-parse --short HEAD)
    echo "Building helm chart for CIRCLE_BUILD_NUM $CIRCLE_BUILD_NUM version ${version}"
    sed -Ei='' "/(^version|appVersion): /s/^(version|appVersion): .*/\1: $version/" "${TEMPDIR}/astronomer/Chart.yaml" "${TEMPDIR}/astronomer/charts/astronomer/Chart.yaml"
    sed -i='' "s#^description: .*#description: $(date "+%FT%T%z") ${CIRCLE_BRANCH} ${CIRCLE_BUILD_URL} https://github.com/astronomer/astronomer/commits/${CIRCLE_SHA1}#" "${TEMPDIR}/astronomer/Chart.yaml"
    bin/repo-state-report.sh > "${TEMPDIR}/astronomer/repo_state.log"
  fi
fi

helm package "${TEMPDIR}/astronomer"
