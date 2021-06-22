#!/usr/bin/env bash
# Build the astronomer helm chart based off of the current git branch
#
# https://circleci.com/docs/2.0/env-vars/#built-in-environment-variables

set -x
set -e

TEMPDIR="${TEMPDIR:-/tmp/astro-temp}"
git_root="$(git rev-parse --show-toplevel)"
app_version=$(awk '$1 == "appVersion:" {print $2}' "${git_root}/values.yaml")

helm repo add kedacore https://kedacore.github.io/charts
rm -rf "${TEMPDIR}/astronomer" || true
mkdir -p "${TEMPDIR}"
cp -R "${git_root}" "${TEMPDIR}/"
find "${TEMPDIR}/astronomer/charts" -name requirements.yaml -execdir helm dep update \;

if [[ "${CIRCLE_BRANCH}" =~ release-[0-9]+\.[0-9]+ ]] ; then
  version=$(awk '$1 ~ /^version/ {printf $2}' "${TEMPDIR}/astronomer/Chart.yaml")
  echo "Doing internal release for CIRCLE_BRANCH ${CIRCLE_BRANCH} version ${version}"
else
  version=$(awk '$1 ~ /^version/ {printf "%s-build%s\n", $2, ENVIRON["CIRCLE_BUILD_NUM"]}' "${TEMPDIR}/Chart.yaml")
  echo "Doing internal release for CIRCLE_BUILD_NUM $CIRCLE_BUILD_NUM version ${version}"
  extra_args=( '--version' "${version}" )
  short_git_url=$(curl -sS -i https://git.io -F "url=https://github.com/astronomer/astronomer/commits/${CIRCLE_SHA1}" | awk '$1 == "Location:" {print $2}')
  sed -i "s#^description: .*#description: $(date "+%FT%T%z") ${short_git_url} ${CIRCLE_BRANCH} ${CIRCLE_BUILD_URL}#" "${TEMPDIR}/Chart.yaml"
fi

helm package "${TEMPDIR}/astronomer" --dependency-update --app-version "${app_version}" "${extra_args[@]}"
